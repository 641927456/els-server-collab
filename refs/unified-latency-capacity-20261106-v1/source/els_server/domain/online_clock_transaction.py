"""One durable commit for the two clocks observing the same selected save.

Each provider retains its owner/rule checks and its own savepoint. A cursor
which participated in a failed physical commit is restored before returning;
the next ordinary observation still includes its entire pending interval.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import logging,sqlite3
from els_server.performance import clock_stage,sqlite_observed
from els_server.storage.sqlite_timing import begin_write,commit_write,end_write
from els_server.storage.writer_errors import caller_error

_current=ContextVar('selected_online_clock_commit',default=None)
def current_commit():return _current.get()

class _ClockCommit:
    def __init__(self,stop,writer=None):
        self.stop=stop;self.db=None;self.lease=None;self.path=None;self.index=0
        self.serial=0;self.written=[];self.committed=False
        self.batch_writer=writer;self.plans=[];self.errors=[]

    def persist(self,clock,path,write):
        if self.batch_writer is None:
            with self.writer(clock,path)as db:write(db)
            return
        path=Path(path).resolve()
        if self.path is None:self.path=path
        elif path!=self.path:raise ValueError('Online pair selected save differs')
        self.plans.append((self.index,clock,dict(vars(clock)),path,write))

    def _restore_one(self,clock,before,*,busy):
        clock.__dict__.clear();clock.__dict__.update(before)
        if busy:clock._deferred=clock._attempt
        if self.stop:clock.closed=True;clock.identity=None

    @contextmanager
    def writer(self,clock,path):
        path=Path(path).resolve()
        if self.db is None:
            with clock_stage('online_pair_connect'):db=sqlite3.connect(path,timeout=10 if self.stop else 0)
            try:
                with clock_stage('online_pair_begin'):lease=begin_write(db)
            except BaseException:db.close();raise
            self.db,self.lease,self.path=db,lease,path
        elif path!=self.path:raise ValueError('Online pair selected save differs')
        before=dict(vars(clock));name='pair_clock_'+str(self.serial);self.serial+=1
        self.db.execute('SAVEPOINT '+name)
        try:yield self.db
        except BaseException:
            self.db.execute('ROLLBACK TO '+name);self.db.execute('RELEASE '+name);raise
        else:
            self.db.execute('RELEASE '+name);self.written.append((self.index,clock,before))

    def finish(self):
        if self.batch_writer is not None:
            if not self.plans:return
            with clock_stage('online_pair_commit'):
                results,physical=self.batch_writer.commit(tuple((path,write)for _,_,_,path,write in self.plans),stop=self.stop)
            for(index,clock,before,path,write),error in zip(self.plans,results):
                if error is None:self.written.append((index,clock,before));continue
                code=getattr(error,'sqlite_errorcode',None)
                busy=type(code)is int and code&255 in(sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)
                self._restore_one(clock,before,busy=busy and not self.stop)
                if busy and not self.stop:
                    sqlite_observed(busy=True)
                    logging.getLogger(__name__).debug('Online pair provider deferred: SQLite code=%s',code)
                else:self.errors.append((index,caller_error(error)))
            if physical is not None:raise caller_error(physical)from physical
            self.committed=True;return
        if self.db is None:return
        failed=True
        try:
            with clock_stage('online_pair_commit'):commit_write(self.db)
            self.committed=True;failed=False
        except BaseException:self.db.rollback();raise
        finally:
            end_write(self.lease,failed=failed);self.db.close();self.db=None

    def restore(self,*,busy):
        if self.committed:return
        for _,clock,before in self.written:
            self._restore_one(clock,before,busy=busy)

def observe_clocks(clocks,session,*,stop=False):
    writer=getattr(getattr(session,'application',None),'clock_writer',None)
    scope=_ClockCommit(stop,writer);token=_current.set(scope);errors=[]
    try:
        for index,clock in enumerate(clocks):
            scope.index=index
            try:clock.observe(session,stop=stop)
            except BaseException as error:errors.append((index,error))
        try:scope.finish()
        except BaseException as error:
            code=getattr(error,'sqlite_errorcode',None)
            busy=type(code)is int and code&255 in(sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)
            scope.restore(busy=busy)
            if busy and not stop:
                sqlite_observed(busy=True)
                logging.getLogger(__name__).debug('Online pair commit deferred: SQLite code=%s',code)
            else:errors.append((min((i for i,_,_ in scope.written),default=len(clocks)),error))
        finally:errors.extend(scope.errors)
    finally:_current.reset(token)
    if errors:raise min(errors,key=lambda value:value[0])[1]
