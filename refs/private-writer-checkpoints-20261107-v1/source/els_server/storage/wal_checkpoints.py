"""Drain WAL pages in the background before a player COMMIT reaches its threshold.

PASSIVE never waits for readers/writers. Application-owned writer connections
retain FULL sync and leave checkpoint work here for their entire lifetime.
Application drains and closes those writers before stopping this worker.
"""
from concurrent.futures import Future
from contextlib import closing
from pathlib import Path
from threading import Event,Lock,Thread
import sqlite3,time,sys

class WALCheckpoints:
    def __init__(self,path):
        self.path=Path(path);self.stop=Event();self.lock=Lock()
        self.ready=Future();self.finished=Future();self.started=False
        self.binding=None
        self.background_thread_priority=None
        self.thread=Thread(target=self._run,name='els-wal-checkpoint')
        self.runs=0;self.busy=0;self.maximum_ms=0.;self.total_ms=0.;self.last_ms=0.;self.last=None

    def prepare(self):
        self.started=True;self.thread.start()
        try:self.ready.result()
        except BaseException:
            self.thread.join();raise

    def require_active(self):
        if not self.ready.done():raise RuntimeError('Save checkpoint is not ready')
        self.ready.result()
        if self.finished.done():
            self.finished.result()
            raise RuntimeError('Save checkpoint is not running')

    def configure_writer(self,db,path):
        # Called only when a private writer opens its owned connection,
        # before any transaction. No policy SQL runs after an economic COMMIT.
        self.require_active()
        info=path.stat()
        if (path,info.st_dev,info.st_ino)!=self.binding:
            raise ValueError('Save checkpoint database binding changed')
        db.execute('PRAGMA wal_autocheckpoint=0')

    def _run(self):
        try:
            if sys.platform=='win32':
                import ctypes
                kernel=ctypes.WinDLL('kernel32',use_last_error=True)
                kernel.GetCurrentThread.restype=ctypes.c_void_p
                kernel.SetThreadPriority.argtypes=[ctypes.c_void_p,ctypes.c_int]
                kernel.SetThreadPriority.restype=ctypes.c_int
                kernel.GetThreadPriority.argtypes=[ctypes.c_void_p]
                kernel.GetThreadPriority.restype=ctypes.c_int
                thread=kernel.GetCurrentThread()
                # This thread shares the save file and SQLite WAL locks with
                # foreground commits. Background mode also throttles I/O and
                # can hold those shared resources behind low-priority I/O.
                # Lower only CPU priority; keep disk I/O at the normal level.
                if not kernel.SetThreadPriority(thread,-1):raise ctypes.WinError(ctypes.get_last_error())
                priority=kernel.GetThreadPriority(thread)
                if priority==0x7fffffff:raise ctypes.WinError(ctypes.get_last_error())
                self.background_thread_priority=priority
            path=self.path.resolve()
            with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=0))as db:
                info=path.stat();self.binding=(path,info.st_dev,info.st_ino)
                while True:
                    started=time.perf_counter()
                    row=tuple(db.execute('PRAGMA main.wal_checkpoint(PASSIVE)').fetchone())
                    with self.lock:
                        self.runs+=1;self.busy+=row[0];self.last=row
                        self.last_ms=(time.perf_counter()-started)*1000
                        self.total_ms+=self.last_ms;self.maximum_ms=max(self.maximum_ms,self.last_ms)
                    if not self.ready.done():self.ready.set_result(None)
                    if self.stop.wait(.25):break
        except BaseException as error:
            if not self.ready.done():self.ready.set_exception(error)
            self.finished.set_exception(error)
        else:self.finished.set_result(None)

    def check(self):
        if self.finished.done():self.finished.result()

    def snapshot(self):
        self.check()
        with self.lock:return dict(prewarmed=self.ready.done()and self.ready.exception()is None,runs=self.runs,busy=self.busy,maximum_ms=self.maximum_ms,total_ms=self.total_ms,last_ms=self.last_ms,interval_ms=250,background_thread_priority=self.background_thread_priority,last=self.last)

    def close(self):
        if self.started:
            self.stop.set();self.thread.join();self.finished.result()
