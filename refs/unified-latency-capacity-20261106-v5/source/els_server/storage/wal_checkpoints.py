"""Drain WAL pages in the background before a player COMMIT reaches its threshold.

PASSIVE never waits for readers/writers. Every economic COMMIT retains FULL sync
and SQLite's original automatic checkpoint; this worker changes no player rows.
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
        self.background_thread_priority=None
        self.thread=Thread(target=self._run,name='els-wal-checkpoint')
        self.runs=0;self.busy=0;self.maximum_ms=0.;self.total_ms=0.;self.last_ms=0.;self.last=None

    def prepare(self):
        self.started=True;self.thread.start()
        try:self.ready.result()
        except BaseException:
            self.thread.join();raise

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
                if not kernel.SetThreadPriority(thread,0x10000):raise ctypes.WinError(ctypes.get_last_error())
                priority=kernel.GetThreadPriority(thread)
                if priority==0x7fffffff:raise ctypes.WinError(ctypes.get_last_error())
                self.background_thread_priority=priority
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=rw',uri=True,timeout=0))as db:
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
