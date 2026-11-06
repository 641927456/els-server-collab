"""Private ground-coin commits; callers retain their actor until real retirement."""
from concurrent.futures import Future
from pathlib import Path
from queue import Queue,Empty
from threading import Lock,Thread
from collections import deque
import sqlite3
from els_server.performance import clock_stage,worker_timing
from els_server.storage.sqlite_timing import write_transaction,batch_should_yield
from els_server.storage.read_scope import ReadConnections,committed_reads,canonical_path,snapshot_connection
from els_server.storage.writer_errors import writer_result


class CoinWriter:
    def __init__(self,path):
        self.path=Path(path);self.queue=Queue(16);self.lock=Lock();self.closed=False
        self.ready=deque()
        self.batches=0;self.claims=0;self.max_batch=0
        self.failed_batches=0;self.timings=deque(maxlen=256);self.metrics_lock=Lock()
        self.prepared=False
        self.read_connections=ReadConnections()
        self.thread=Thread(target=self._run,name='els-coin-writer');self.thread.start()

    def claim(self,store,operation,proof,*,drop_id,template,ed,dungeon):
        from els_server.domain.drop_pickup import GROUND_ED
        from els_server.storage.reward_state import RewardState
        if type(store)is not RewardState or template not in GROUND_ED:raise ValueError('Ground coin writer source')
        path=canonical_path(store.path)
        if path!=canonical_path(self.path):raise ValueError('Ground coin writer database binding')
        binding=(store.uid,store.account_id,path);future=Future()
        with self.lock:
            if self.closed:raise RuntimeError('Ground coin writer closed')
            self.queue.put((store,binding,operation,proof,drop_id,template,ed,dungeon,future))
        with clock_stage('coin_commit'):return writer_result(future)

    def prepare(self):
        future=Future()
        with self.lock:
            if self.closed:raise RuntimeError('Ground coin writer closed')
            self.queue.put(future)
        return writer_result(future)

    def _connection(self,db,binding):
        path=self.path.resolve();info=path.stat();current=(path,info.st_dev,info.st_ino)
        if current!=binding:
            if db is not None:db.close()
            db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10)
        return db,current

    @staticmethod
    def _grant(db,job):
        from els_server.domain.dungeon_drops import ground_pickup_notice
        from els_server.protocol.local_messages import client_economy_fields
        store,binding,operation,proof,drop_id,template,ed,dungeon,_=job
        def current():
            if (store.uid,store.account_id,canonical_path(store.path))!=binding:raise ValueError('Ground coin selected store changed')
        current()
        def encode(balances,economy):
            current();client_economy_fields(balances)
            return ground_pickup_notice(drop_id,binding[0],template=template,ed=ed,bonus_ed=economy['bonus_ed']).payload
        # No item/raid/attendance source or caller callback enters this lane.
        # grant retains its original savepoint, title effects and receipt checks.
        result=store.grant(operation,proof,ed,0,response_builder=encode,
            title_economy='ground_ed',title_dungeon=dungeon,transaction=db)
        current();return result

    def _run(self):
        db=None;binding=None
        try:
            while True:
                first=self.ready.popleft()if self.ready else self.queue.get()
                if first is None:return
                if type(first)is Future:
                    try:
                        db,binding=self._connection(db,binding)
                        db.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchone()
                        with committed_reads(connections=self.read_connections):
                            with snapshot_connection(self.path)as reader:
                                reader.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchone()
                        self.prepared=True
                    except BaseException as error:first.set_exception(error)
                    else:first.set_result(None)
                    continue
                jobs=[first];results=[];stopping=False
                timing=dict(projection_ms=0.,projection_hits=0,projection_loads=0,registry_ms=0.,registry_checks=0)
                try:
                    db,binding=self._connection(db,binding)
                    with worker_timing(timing),write_transaction(db):
                        while len(jobs)<16:
                            try:job=self.ready.popleft()if self.ready else self.queue.get_nowait()
                            except Empty:break
                            if job is None:stopping=True;break
                            jobs.append(job)
                        for index,job in enumerate(jobs):
                            savepoint='ground_coin_'+str(index);db.execute('SAVEPOINT '+savepoint)
                            try:
                                with committed_reads(connections=self.read_connections):result=self._grant(db,job)
                                db.execute('RELEASE '+savepoint)
                            except Exception as error:
                                if not db.in_transaction:raise
                                db.execute('ROLLBACK TO '+savepoint);db.execute('RELEASE '+savepoint)
                                results.append((None,error))
                            else:results.append((result,None))
                            # Preserve group commit without monopolizing the
                            # sole writer while another lane is waiting.
                            if batch_should_yield(db):break
                            while not stopping and len(jobs)<16:
                                try:job=self.queue.get_nowait()
                                except Empty:break
                                if job is None:stopping=True;break
                                jobs.append(job)
                    if len(results)<len(jobs):
                        self.ready.extend(jobs[len(results):])
                        if stopping:self.ready.append(None);stopping=False
                        jobs=jobs[:len(results)]
                    self.batches+=1;self.claims+=len(jobs);self.max_batch=max(self.max_batch,len(jobs))
                except BaseException as error:
                    self.failed_batches+=1;results=[(None,error)]*len(jobs)
                with self.metrics_lock:self.timings.append(timing)
                for job,(result,error)in zip(jobs,results):
                    if error is None:job[-1].set_result(result)
                    else:job[-1].set_exception(error)
                if stopping:return
        finally:
            try:
                if db is not None:db.close()
            finally:self.read_connections.close()

    def snapshot(self):
        with self.metrics_lock:
            result=dict(batches=self.batches,claims=self.claims,max_batch=self.max_batch,pending=self.queue.qsize()+len(self.ready),failed_batches=self.failed_batches,prewarmed=self.prepared)
            for key in('sql_gate_wait_ms','sql_writer_held_ms','sql_finish_wait_ms'):
                values=sorted(row.get(key,0.)for row in self.timings)
                result[key+'_p95']=values[(95*len(values)+99)//100-1]if values else 0.
            return result

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True;self.queue.put(None)
        self.thread.join()
