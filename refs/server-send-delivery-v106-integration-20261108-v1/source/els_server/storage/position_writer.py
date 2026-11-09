"""Commit fixed location rows, with coordinate-only town write coalescing.

Only location rows enter this lane. It cannot execute callbacks, economic
transactions or prepared actor state. Scene changes retain durable barriers.
"""
from concurrent.futures import Future
from pathlib import Path
from queue import Queue,Empty
from threading import Lock,Thread
import sqlite3
import time
from els_server.storage.sqlite_timing import write_transaction
from els_server.performance import clock_stage
from els_server.storage.writer_errors import writer_result


def save_row(db,uid,values):
    row=db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(uid,)).fetchone()
    if row is None:raise ValueError('Missing local character state')
    if row[:6]!=values:
        row=db.execute('UPDATE location SET town=?,board=?,progress=?,x=?,y=?,z=?,revision=revision+1 WHERE uid=? RETURNING town,board,progress,x,y,z,revision',(*values,uid)).fetchone()
    return {'map':row[0],'board':row[1],'progress':row[2],'xyz':tuple(row[3:6]),'revision':row[6]}


POSITION_BATCH=64


class PositionWriter:
    def __init__(self,path,*,checkpoints=None):
        self.path=Path(path);self.queue=Queue(POSITION_BATCH);self.lock=Lock();self.closed=False
        self.checkpoints=checkpoints
        self.batches=0;self.positions=0;self.max_batch=0
        self.thread=Thread(target=self._run,name='els-position-writer')
        self.thread.start()
        from els_server.storage.town_position_buffer import TownPositions
        self.town=TownPositions(self);self.close_lock=Lock()

    def save(self,path,uid,values):
        self.flush(path,uid)
        with clock_stage('position_commit'):result=writer_result(self._submit(path,uid,values))
        self.town.saved(uid,result)
        return result

    def _submit(self,path,uid,values):
        path=Path(path)
        if path!=self.path and path.resolve()!=self.path.resolve():raise ValueError('Position writer database binding')
        future=Future()
        with self.lock:
            if self.closed:raise RuntimeError('Position writer closed')
            self.queue.put((uid,values,future))
        return future

    def defer(self,path,uid,values):
        path=Path(path)
        if path!=self.path and path.resolve()!=self.path.resolve():raise ValueError('Position writer database binding')
        self.town.record(uid,tuple(values))

    def flush(self,path,uid,*,consume=False):
        if not self.town.needs_barrier(uid,consume=consume):return None
        path=Path(path)
        if path!=self.path and path.resolve()!=self.path.resolve():raise ValueError('Position writer database binding')
        return self.town.flush(uid,consume=consume)

    def forget(self,uid):self.town.forget(uid)

    def _run(self):
        db=None;binding=None
        try:
            while True:
                first=self.queue.get()
                if first is None:return
                jobs=[first];results=[];stopping=False
                try:
                    # Collect before taking the sole database writer. Every
                    # actor still waits for the same durable commit; the short
                    # window reduces tiny position commits during town traffic.
                    deadline=time.monotonic()+.002
                    while len(jobs)<POSITION_BATCH:
                        remaining=deadline-time.monotonic()
                        if remaining<=0:break
                        try:job=self.queue.get(timeout=remaining)
                        except Empty:break
                        if job is None:stopping=True;break
                        jobs.append(job)
                    # This private thread executes only save_row, exposes no
                    # connection/callback/authority token, and retains no TX.
                    # Recheck the actual file before each independent batch.
                    path=self.path.resolve();info=path.stat();current=(path,info.st_dev,info.st_ino)
                    if binding!=current:
                        if db is not None:db.close();db=None
                        opened=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10)
                        try:
                            if self.checkpoints is not None:self.checkpoints.configure_writer(opened,path)
                        except BaseException:opened.close();raise
                        db=opened;binding=current
                    elif self.checkpoints is not None:self.checkpoints.require_active()
                    with write_transaction(db):
                        while not stopping and len(jobs)<POSITION_BATCH:
                            try:
                                job=self.queue.get_nowait()
                                if job is None:stopping=True;break
                                jobs.append(job)
                            except Empty:break
                        for uid,values,future in jobs:
                            try:results.append((save_row(db,uid,values),None))
                            except ValueError as error:results.append((None,error))
                    self.batches+=1;self.positions+=len(jobs);self.max_batch=max(self.max_batch,len(jobs))
                except BaseException as error:
                    results=[(None,error)]*len(jobs)
                for(_,_,future),(result,error)in zip(jobs,results):
                    if error is None:future.set_result(result)
                    else:future.set_exception(error)
                if stopping:return
        finally:
            if db is not None:db.close()

    def snapshot(self):
        return dict(batches=self.batches,positions=self.positions,max_batch=self.max_batch,pending=self.queue.qsize(),town=self.town.snapshot())

    def close(self):
        # Application first drains all worker callers, including cancelled
        # sockets. Earlier submissions always retire before this sentinel.
        with self.close_lock:
            if self.closed:return
            try:self.town.close()
            finally:
                with self.lock:self.closed=True;self.queue.put(None)
                self.thread.join()
