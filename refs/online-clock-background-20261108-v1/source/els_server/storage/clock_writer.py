"""Synchronous group commit of already planned online-clock SQL only."""
from concurrent.futures import Future
from contextvars import Context,copy_context
from pathlib import Path
from queue import Queue,Empty
from threading import Lock,Thread
import sqlite3,traceback
from els_server.storage.sqlite_timing import begin_write,commit_write,end_write
from els_server.storage.writer_errors import caller_error,writer_result

class ClockWriter:
    def __init__(self,path,*,checkpoints=None):
        self.path=Path(path);self.queue=Queue(16);self.lock=Lock();self.closed=False
        self.checkpoints=checkpoints
        self.connection=None;self.binding=None;self.prepared=False
        self.jobs_lock=Lock();self.jobs=0;self.nonblocking_deferrals=0
        self.batches=0;self.observations=0;self.maximum_batch=0;self.failed_commits=0
        self.thread=Thread(target=self._run,name='els-clock-writer');self.thread.start()

    def prepare(self):
        future=Future()
        with self.lock:
            if self.closed:raise RuntimeError('Clock writer closed')
            self.queue.put(future)
        return writer_result(future)

    def commit(self,plans,*,stop):
        return writer_result(self.submit(plans,stop=stop))

    def submit(self,plans,*,stop,background=False):
        plans=tuple(plans);future=Future()
        # Non-final observations previously used SQLite timeout=0. Preserve
        # that policy before the private queue too: another durable write
        # must not turn a best-effort clock observation into a long wait.
        if not stop and not self.lock.acquire(blocking=False):
            future.set_result(self._busy_report(plans));return future
        if stop:self.lock.acquire()
        try:
            if self.closed:raise RuntimeError('Clock writer closed')
            with self.jobs_lock:
                busy=not stop and self.jobs>0
                if not busy:self.jobs+=1
            if busy:
                future.set_result(self._busy_report(plans));return future
            # A background observation outlives its periodic worker sample.
            # Its SQL must not mutate that already-published timing context.
            self.queue.put((plans,stop,Context()if background else copy_context(),future))
        finally:self.lock.release()
        return future

    def _busy_report(self,plans):
        if self.closed:raise RuntimeError('Clock writer closed')
        with self.jobs_lock:self.nonblocking_deferrals+=1
        errors=[];expected=self.path.resolve()
        for path,_ in plans:
            if Path(path).resolve()!=expected:error=ValueError('Clock writer selected save differs')
            else:
                error=sqlite3.OperationalError('database is locked')
                error.sqlite_errorcode=sqlite3.SQLITE_BUSY;error.sqlite_errorname='SQLITE_BUSY'
            errors.append(error)
        return tuple(errors),None

    def _connection(self):
        path=self.path.resolve();info=path.stat();binding=(path,info.st_dev,info.st_ino)
        if binding!=self.binding:
            self._close_connection()
            db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=0)
            try:
                if self.checkpoints is not None:self.checkpoints.configure_writer(db,path)
            except BaseException:db.close();raise
            self.connection=db
            self.binding=binding
        elif self.checkpoints is not None:self.checkpoints.require_active()
        return self.connection

    def _close_connection(self):
        db=self.connection;self.connection=None;self.binding=None
        if db is not None:db.close()

    def _run(self):
        try:
            while True:
                first=self.queue.get()
                if first is None:return
                if type(first)is Future:
                    try:self._connection().execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchone();self.prepared=True
                    except BaseException as error:first.set_exception(error)
                    else:first.set_result(None)
                    del first;continue
                stopping,errors=self._commit_ready(first)
                del first
                self._clear_errors(errors)
                del errors
                if stopping:return
        finally:self._close_connection()

    @staticmethod
    def _clear_errors(errors):
        for error in errors:traceback.clear_frames(error.__traceback__)

    def _commit_ready(self,first):
        jobs=[first];stopping=False;reports=[];errors=[];db=None;lease=None;physical_error=None;serial=0
        while len(jobs)<16:
            try:job=self.queue.get_nowait()
            except Empty:break
            if job is None:stopping=True;break
            if type(job)is Future:
                self.queue.put(job);break
            jobs.append(job)
        for plans,stop,context,future in jobs:
            results=[]
            for path,write in plans:
                if physical_error is not None:
                    results.append(physical_error);continue
                try:
                    path=Path(path)
                    if path!=self.path and path.resolve()!=self.path.resolve():raise ValueError('Clock writer selected save differs')
                    if lease is None:
                        db=self._connection();db.execute('PRAGMA busy_timeout='+('10000'if stop else'0'));lease=begin_write(db)
                    name='clock_batch_'+str(serial);serial+=1;db.execute('SAVEPOINT '+name)
                    try:context.run(write,db)
                    except BaseException as error:
                        # FULL/IO errors may abort the outer transaction and
                        # remove every savepoint. Keep that failure for the
                        # whole batch, including previously completed plans.
                        physical_error=error
                        if db.in_transaction:
                            db.execute('ROLLBACK TO '+name);db.execute('RELEASE '+name)
                            physical_error=None
                        raise
                    else:db.execute('RELEASE '+name)
                except BaseException as error:
                    if lease is not None and not db.in_transaction:physical_error=error
                    results.append(error);errors.append(error)
                else:results.append(None)
            reports.append(results)
        if lease is not None:
            failed=True
            try:
                if physical_error is None:commit_write(db);failed=False
                else:db.rollback()
            except BaseException as error:
                physical_error=error;errors.append(error)
                try:db.rollback()
                except BaseException as error:physical_error=error;errors.append(error)
            finally:
                if failed:self.failed_commits+=1
                end_write(lease,failed=failed)
            self.batches+=1;self.observations+=len(jobs);self.maximum_batch=max(self.maximum_batch,len(jobs))
        if physical_error is not None:self._close_connection()
        # Report exceptions are never raised by a caller. Callers construct
        # their own error, so a future cannot acquire an actor traceback.
        with self.jobs_lock:self.jobs-=len(jobs)
        for job,results in zip(jobs,reports):
            job[-1].set_result((tuple(None if error is None else caller_error(error)for error in results),None if physical_error is None else caller_error(physical_error)))
        return stopping,tuple(errors)

    def snapshot(self):
        return dict(prewarmed=self.prepared,batches=self.batches,observations=self.observations,maximum_batch=self.maximum_batch,failed_commits=self.failed_commits,pending=self.queue.qsize(),nonblocking_deferrals=self.nonblocking_deferrals)

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True;self.queue.put(None)
        self.thread.join()
