"""Observe original SQLite writer boundaries, without changing retries or modes."""
from contextlib import contextmanager
import sqlite3
import time
import threading
import sys
from collections import deque
from pathlib import Path
from weakref import WeakValueDictionary
from els_server.performance import sqlite_observed,slow_writer_observed,writer_gate_observed,sqlite_acquire_observed


def _locked():
    error=sqlite3.OperationalError('database is locked')
    error.sqlite_errorcode=sqlite3.SQLITE_BUSY;error.sqlite_errorname='SQLITE_BUSY'
    return error


class _WriterTurn:
    def __init__(self):
        self.lock=threading.Lock();self.waiters=deque();self.active=False
        self.history=deque(maxlen=64)
    def enter(self,deadline,source='unknown'):
        ticket=threading.Event();ticket.source=source;ticket.started=None
        queued=time.perf_counter()
        try:
            with self.lock:
                self.waiters.append(ticket)
                if not self.active:
                    self.active=True;ticket.started=time.perf_counter()
                    return ticket
            try:
                ticket.wait(max(0.,deadline-time.monotonic()))
                with self.lock:
                    # A release may win the deadline race. As with the previous
                    # condition loop, an already-admitted head owns its turn.
                    if ticket.is_set():return ticket
                raise _locked()
            except BaseException:
                with self.lock:
                    if self.waiters[0]is ticket:
                        self._retire();self._handoff()
                    else:self.waiters.remove(ticket)
                raise
        finally:
            ended=time.perf_counter()
            if ended-queued>=.05:
                with self.lock:
                    spans=list(self.history)
                    if self.waiters:
                        head=self.waiters[0]
                        spans.append((head.started,ended,head.source,head is ticket))
                # Clip to this wait; never blame our own reserved turn or a
                # later transaction. Source strings contain no actor/SQL data.
                stop=min(ended,ticket.started)if ticket.started is not None else ended
                overlap=[(source,max(0.,min(stop,end)-max(queued,start)))
                    for start,end,source,own in spans if not own]
                writer_gate_observed(ended-queued,overlap)
    def _retire(self):
        head=self.waiters.popleft()
        self.history.append((head.started,time.perf_counter(),head.source,False))
    def _handoff(self):
        self.active=bool(self.waiters)
        if self.active:
            self.waiters[0].started=time.perf_counter();self.waiters[0].set()
    def leave(self,ticket):
        with self.lock:
            assert self.active and self.waiters[0]is ticket
            # Reserve the head before waking it; new arrivals cannot cut in.
            self._retire();self._handoff()

    def contended(self):
        with self.lock:return len(self.waiters)>1


_catalog_lock=threading.Lock();_turns=WeakValueDictionary();_leases=threading.local()


def _writer_turn(db):
    filename=next(row[2]for row in db.execute('PRAGMA database_list')if row[1]=='main')
    if not filename:return None
    path=Path(filename).resolve()
    with _catalog_lock:
        turn=_turns.get(path)
        if turn is None:turn=_WriterTurn();_turns[path]=turn
        return turn


class _WriteLease:
    def __init__(self,started,db,turn,ticket):self.started=started;self.db=db;self.turn=turn;self.ticket=ticket
    def release(self):
        # Explicit commits release before connection close; rollback/finally
        # retires the same lease when no commit completed.
        if self.turn is not None:
            self.turn.leave(self.ticket);self.turn=None


def _busy(error):
    code=getattr(error,'sqlite_errorcode',None)
    return type(code) is int and code & 255 in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)


def commit_write(db):
    started=time.perf_counter();busy=False
    try:
        result=db.commit()
        lease=getattr(_leases,'values',{}).get(db)
        if lease is not None:lease.release()
        return result
    except BaseException as error:
        busy=_busy(error);raise
    finally:sqlite_observed(finish=time.perf_counter()-started,busy=busy,finish_busy=busy)


def begin_write(db):
    started=time.perf_counter();turn=None;ticket=None;gate_started=None;engine_started=None;original_timeout=None;source='unknown'
    try:
        # Preserve SQLite's existing immediate error for a nested BEGIN.
        if db.in_transaction:db.execute('BEGIN IMMEDIATE')
        original_timeout=db.execute('PRAGMA busy_timeout').fetchone()[0]
        deadline=time.monotonic()+original_timeout/1000
        turn=_writer_turn(db)
        gate_started=time.perf_counter()
        if turn is not None:
            caller=sys._getframe(1)
            if caller.f_code is write_transaction.__wrapped__.__code__:
                caller=caller.f_back.f_back
            source=Path(caller.f_code.co_filename).name+':'+caller.f_code.co_name
            del caller
            ticket=turn.enter(deadline,source)
        engine_started=time.perf_counter()
        sqlite_observed(gate_wait=engine_started-gate_started)
        remaining=max(0,int((deadline-time.monotonic())*1000))
        db.execute('PRAGMA busy_timeout='+str(remaining))
        try:
            executing=time.perf_counter();failed=True;busy=False
            try:
                db.execute('BEGIN IMMEDIATE');failed=False
            except BaseException as error:
                busy=_busy(error);raise
            finally:
                elapsed=time.perf_counter()-executing
                sqlite_acquire_observed(source,elapsed,failed,busy)
        finally:db.execute('PRAGMA busy_timeout='+str(original_timeout))
    except BaseException as error:
        if engine_started is None and gate_started is not None:sqlite_observed(gate_wait=time.perf_counter()-gate_started)
        if ticket is not None:turn.leave(ticket)
        sqlite_observed(wait=time.perf_counter()-started,busy=_busy(error))
        raise
    acquired=time.perf_counter();sqlite_observed(wait=acquired-started,engine_wait=acquired-engine_started)
    lease=_WriteLease(acquired,db,turn,ticket)
    if not hasattr(_leases,'values'):_leases.values={}
    _leases.values[db]=lease
    return lease


def end_write(acquired,*,failed=False):
    try:sqlite_observed(held=time.perf_counter()-acquired.started,rollback=failed)
    finally:
        acquired.release()
        values=getattr(_leases,'values',{})
        if values.get(acquired.db)is acquired:del values[acquired.db]


def batch_should_yield(db):
    """Finish a ready batch after 4 ms if another writer has reserved a turn.

    Never interrupt a job or its atomic transaction. This limits additional
    work admitted to the current commit; the existing FIFO chooses who runs
    next. With no competing writer the original sixteen-job batch remains.
    """
    lease=getattr(_leases,'values',{}).get(db)
    return (lease is not None and lease.turn is not None
        and time.perf_counter()-lease.started>=.004 and lease.turn.contended())


@contextmanager
def write_transaction(db):
    acquired=begin_write(db)
    failed=True;finished=None
    try:
        with db:
            yield db
            finished=time.perf_counter()
        failed=False
    except BaseException as error:
        busy=_busy(error)
        sqlite_observed(busy=busy,finish_busy=busy and finished is not None)
        raise
    finally:
        ended=time.perf_counter()
        if finished is not None:sqlite_observed(finish=ended-finished)
        end_write(acquired,failed=failed)
        if ended-acquired.started>=.05:
            # Resuming this context manager comes through contextlib.__exit__.
            # Keep only the owning function name after releasing its writer;
            # never retain frames, SQL text, account data or player payloads.
            code=sys._getframe(2).f_code
            source=Path(code.co_filename).name+':'+code.co_name
            slow_writer_observed(source,ended-acquired.started,
                                 ended-finished if finished is not None else 0.,failed)


@contextmanager
def read_transaction(db):
    # The caller opens a query_only connection before entering this branch.
    # Its projection and pre-encoding still share an ordinary read snapshot.
    if db.execute('PRAGMA query_only').fetchone() != (1,):
        raise ValueError('Projection requires query-only connection')
    with db:
        db.execute('BEGIN')
        yield db
