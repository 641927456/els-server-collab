"""Exclusive save ownership and SQLite health checks without replacing data."""
from contextlib import closing
import os
import sqlite3


class SaveLease:
    def __init__(self,path):self.path=path;self.handle=None

    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        handle=open(str(self.path)+'.lock','a+b')
        if os.fstat(handle.fileno()).st_size==0:handle.write(b'\0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            handle.close()
            raise RuntimeError('Save already owned by another server: '+str(self.path)) from error
        self.handle=handle
        return self

    def __exit__(self,*args):
        if self.handle:
            self.handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(),fcntl.LOCK_UN)
            self.handle.close();self.handle=None


def prepare_database(path):
    # WAL is persistent; existing transaction/receipt schemas remain authoritative.
    with closing(sqlite3.connect(path,timeout=10)) as db:
        result=db.execute('PRAGMA quick_check').fetchall()
        if result!=[('ok',)]:raise RuntimeError('SQLite integrity check failed: '+repr(result))
        if db.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower()!='wal':
            raise RuntimeError('Unable to enable SQLite WAL')


def checkpoint_database(path):
    with closing(sqlite3.connect(path,timeout=10)) as db:
        return list(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())
