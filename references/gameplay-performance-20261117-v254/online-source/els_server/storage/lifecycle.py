"""Exclusive save ownership and SQLite health checks without replacing data."""
from contextlib import closing
import os
import sqlite3
import time


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


class DatabasePreparationStopped(Exception):
    """The owner requested normal shutdown during startup-only reads."""


def prepare_database(path,*,stop_requested=None):
    # WAL is persistent; existing transaction/receipt schemas remain authoritative.
    if stop_requested is not None and stop_requested():raise DatabasePreparationStopped()
    with closing(sqlite3.connect(path,timeout=10)) as db:
        interrupted=False;next_poll=0.
        def progress():
            nonlocal interrupted,next_poll
            now=time.monotonic()
            if now>=next_poll:
                next_poll=now+.25
                interrupted=bool(stop_requested())
            return int(interrupted)
        if stop_requested is not None:db.set_progress_handler(progress,10000)
        try:
            result=db.execute('PRAGMA quick_check').fetchall()
        except sqlite3.OperationalError as error:
            if interrupted and error.sqlite_errorcode==sqlite3.SQLITE_INTERRUPT:
                raise DatabasePreparationStopped() from error
            raise
        finally:
            if stop_requested is not None:db.set_progress_handler(None,0)
        # Remove the callback before the original WAL/index writes. A stopped
        # boot never serves players with an incomplete integrity check.
        if result!=[('ok',)]:raise RuntimeError('SQLite integrity check failed: '+repr(result))
        if stop_requested is not None and stop_requested():raise DatabasePreparationStopped()
        if db.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower()!='wal':
            raise RuntimeError('Unable to enable SQLite WAL')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone():
            db.execute('CREATE INDEX IF NOT EXISTS inventory_action_receipts_kind_owner ON inventory_action_receipts(kind,owner)')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='activity518_facts'").fetchone():
            db.execute('CREATE INDEX IF NOT EXISTS activity518_facts_account_period ON activity518_facts(campaign,account,period)')
            db.execute('CREATE INDEX IF NOT EXISTS activity518_facts_account_cursor ON activity518_facts(campaign,account)')


def checkpoint_database(path):
    with closing(sqlite3.connect(path,timeout=10)) as db:
        return list(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())
