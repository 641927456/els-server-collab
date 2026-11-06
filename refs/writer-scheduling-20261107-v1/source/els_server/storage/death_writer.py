"""Durably commit ready, independent solo-death preparations together.

Every producer retains its original actor/domain ownership until submit returns.
Preparations may change SQL and their private shadow only. No actor adoption or
native reply occurs before the shared commit. The writer owns its SQL connection.
"""
from concurrent.futures import Future
from collections import deque
from contextvars import copy_context
from pathlib import Path
from queue import Queue,Empty
from threading import Lock,Thread
import sqlite3,time,traceback
from els_server.performance import clock_stage
from els_server.storage.sqlite_timing import write_transaction,batch_should_yield
from els_server.storage.read_scope import committed_reads
from els_server.storage.writer_errors import writer_result


class DeathWriter:
    def __init__(self,path,read_connections):
        self.path=Path(path);self.read_connections=read_connections
        self.queue=Queue(16);self.lock=Lock();self.closed=False
        self.ready=deque()
        self.batches=0;self.deaths=0;self.maximum_batch=0;self.failed=0;self.maximum_commit_ms=0.
        self.connection=None;self.binding=None;self.prepared=False
        self.thread=Thread(target=self._run,name='els-death-writer');self.thread.start()

    def submit(self,path,prepare):
        if Path(path).resolve()!=self.path.resolve():raise ValueError('Death writer database binding')
        future=Future()
        with self.lock:
            if self.closed:raise RuntimeError('Death writer closed')
            self.queue.put((prepare,copy_context(),future))
        with clock_stage('death_commit'):return writer_result(future)

    def _run(self):
        try:
            while True:
                first=self.ready.popleft()if self.ready else self.queue.get()
                if first is None:return
                if type(first)is Future:
                    try:
                        db=self._connection();db.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchone()
                        if first.read_preparation is not None:first.read_preparation()
                        self.prepared=True
                    except BaseException as error:first.set_exception(error)
                    else:first.set_result(None)
                    finally:first.read_preparation=None
                    del first
                    continue
                stopping,errors=self._commit_ready(first)
                del first
                self._clear_errors(errors)
                del errors
                if stopping:return
        finally:
            db=self.connection;self.connection=None;self.binding=None
            if db is not None:db.close()

    def _connection(self):
        # Reuse only SQL statements. Re-resolve the kernel path and file
        # identity before every batch; no player projection survives here.
        path=self.path.resolve();info=path.stat();binding=(path,info.st_dev,info.st_ino)
        if self.binding!=binding:
            db=self.connection;self.connection=None;self.binding=None
            if db is not None:db.close()
            self.connection=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10)
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.binding=binding
        return self.connection

    def prepare(self,read_preparation=None):
        future=Future();future.read_preparation=read_preparation
        with self.lock:
            if self.closed:raise RuntimeError('Death writer closed')
            self.queue.put(future)
        return writer_result(future)

    @staticmethod
    def _clear_errors(errors):
        for error in errors:traceback.clear_frames(error.__traceback__)

    def _commit_ready(self,first):
        # Keep actor callbacks and captured contexts in this finite batch
        # frame, never in the idle thread waiting for its next queue item.
        jobs=[first];results=[];stopping=False;started=time.perf_counter()
        try:
            db=self._connection()
            with write_transaction(db):
                while len(jobs)<16:
                    try:job=self.ready.popleft()if self.ready else self.queue.get_nowait()
                    except Empty:break
                    if job is None:stopping=True;break
                    jobs.append(job)
                for index,(prepare,context,future)in enumerate(jobs):
                    name='death_'+str(index);db.execute('SAVEPOINT '+name)
                    def invoke():
                        with committed_reads(connections=self.read_connections):return prepare(db)
                    try:result=context.run(invoke)
                    except BaseException as error:
                        db.execute('ROLLBACK TO '+name);db.execute('RELEASE '+name)
                        results.append((None,error))
                    else:
                        db.execute('RELEASE '+name);results.append((result,None))
                    # Retain a yielded suffix privately in its original order.
                    # No actor is released and no future succeeds for that
                    # suffix until its own transaction actually commits.
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
            self.batches+=1;self.deaths+=sum(error is None for _,error in results)
            self.maximum_batch=max(self.maximum_batch,len(jobs))
        except BaseException as error:
            results=[(None,error)]*len(jobs)
            # A failed whole transaction retires its handle, as the former
            # per-batch connection did. The next job never inherits it.
            db=self.connection;self.connection=None;self.binding=None
            if db is not None:
                try:db.close()
                except BaseException as error:results=[(None,error)]*len(jobs)
        self.maximum_commit_ms=max(self.maximum_commit_ms,(time.perf_counter()-started)*1000)
        for(_,_,future),(result,error)in zip(jobs,results):
            if error is None:future.set_result(result)
            else:self.failed+=1;future.set_exception(error)
        return stopping,tuple(error for _,error in results if error is not None)


    def snapshot(self):
        return dict(batches=self.batches,deaths=self.deaths,maximum_batch=self.maximum_batch,
            failed=self.failed,maximum_commit_ms=self.maximum_commit_ms,pending=self.queue.qsize()+len(self.ready),prewarmed=self.prepared)

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True;self.queue.put(None)
        self.thread.join()
