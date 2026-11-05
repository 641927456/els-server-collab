"""Coalesce only town walking coordinates; explicit barriers wait for SQL."""
from dataclasses import dataclass
from threading import Condition,Thread
import time
from els_server.storage.writer_errors import caller_error as _caller_error


@dataclass
class _Position:
    sequence:int=0
    committed:int=0
    delivered:int=0
    pending:tuple|None=None
    due:float=0.
    row:dict|None=None
    error:BaseException|None=None
    inflight:bool=False
    latest:tuple|None=None


class TownPositions:
    def __init__(self,writer):
        self.writer=writer;self.condition=Condition();self.rows={};self.closed=False
        self.accepted=0;self.coalesced=0;self.failed=0;self.deadline=None
        self.thread=Thread(target=self._run,name='els-town-position-buffer')
        self.thread.start()

    def record(self,uid,values):
        with self.condition:
            if self.closed:raise RuntimeError('Town position buffer closed')
            state=self.rows.get(uid)
            if state is None:state=_Position();self.rows[uid]=state
            if state.error is not None:raise _caller_error(state.error)from state.error
            if state.latest==values:return
            wake=not any(row.pending is not None for row in self.rows.values())
            if state.pending is None:
                if self.deadline is None:self.deadline=time.monotonic()+.1
                state.due=self.deadline
            else:self.coalesced+=1
            state.sequence+=1;state.pending=state.latest=values;self.accepted+=1
            if wake:self.condition.notify_all()

    def needs_barrier(self,uid,*,consume):
        with self.condition:
            state=self.rows.get(uid)
            return state is not None and (state.error is not None or state.pending is not None
                or state.inflight or not consume or state.delivered<state.sequence)

    def flush(self,uid,*,consume=False):
        with self.condition:
            state=self.rows.get(uid)
            if state is None:return None
            target=state.sequence
            if state.pending is not None:state.due=0.;self.condition.notify_all()
            while state.committed<target and state.error is None:self.condition.wait()
            if state.error is not None:raise _caller_error(state.error)from state.error
            if consume:
                if state.delivered>=target:return None
                state.delivered=state.committed
            return None if state.row is None else dict(state.row)

    def saved(self,uid,row):
        with self.condition:
            state=self.rows.get(uid)
            if state is not None:
                state.row=dict(row)
                if state.pending is None and not state.inflight:state.latest=(row['map'],row['board'],row['progress'],*row['xyz'])

    def forget(self,uid):
        with self.condition:
            state=self.rows.get(uid)
            if state is None:return
            if state.inflight or state.pending is not None:raise RuntimeError('Town position has not retired')
            del self.rows[uid]

    def _run(self):
        while True:
            with self.condition:
                while True:
                    pending=[(uid,row)for uid,row in self.rows.items()if row.pending is not None]
                    if self.closed and not pending:return
                    now=time.monotonic()
                    ready=[(uid,row)for uid,row in pending if self.closed or row.due<=now]
                    if ready:break
                    deadline=min((row.due for _,row in pending),default=None)
                    self.condition.wait(None if deadline is None else max(0.,deadline-now))
                jobs=[]
                for uid,state in ready:
                    jobs.append((uid,state,state.sequence,state.pending))
                    state.pending=None;state.inflight=True
                self.deadline=min((row.due for row in self.rows.values()if row.pending is not None),default=None)
            submitted=[]
            for uid,state,sequence,values in jobs:
                try:future=self.writer._submit(self.writer.path,uid,values);error=None
                except BaseException as error:
                    submitted.append((uid,state,sequence,None,error));continue
                submitted.append((uid,state,sequence,future,None))
            for uid,state,sequence,future,error in submitted:
                result=None
                if error is None:
                    try:result=future.result()
                    except BaseException as caught:error=caught
                with self.condition:
                    state.inflight=False
                    if error is None:state.committed=sequence;state.row=result
                    else:
                        state.error=error;state.pending=None;self.failed+=1
                    self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            return dict(accepted_moves=self.accepted,coalesced_moves=self.coalesced,
                pending_actors=sum(row.pending is not None for row in self.rows.values()),
                inflight_actors=sum(row.inflight for row in self.rows.values()),
                retained_actors=len(self.rows),failed=self.failed)

    def close(self):
        with self.condition:
            self.closed=True;self.condition.notify_all()
        self.thread.join()
        with self.condition:errors=[row.error for row in self.rows.values()if row.error is not None]
        if errors:raise BaseExceptionGroup('Town positions could not be saved',errors)
