"""Observe original SQLite writer boundaries, without changing retries or modes."""
from contextlib import contextmanager
import sqlite3
import time
from els_server.performance import sqlite_observed


def _busy(error):
    code=getattr(error,'sqlite_errorcode',None)
    return type(code) is int and code & 255 in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)


def commit_write(db):
    started=time.perf_counter();busy=False
    try:return db.commit()
    except BaseException as error:
        busy=_busy(error);raise
    finally:sqlite_observed(finish=time.perf_counter()-started,busy=busy,finish_busy=busy)


def begin_write(db):
    started=time.perf_counter()
    try:db.execute('BEGIN IMMEDIATE')
    except BaseException as error:
        sqlite_observed(wait=time.perf_counter()-started,busy=_busy(error))
        raise
    acquired=time.perf_counter();sqlite_observed(wait=acquired-started)
    return acquired


def end_write(acquired,*,failed=False):
    sqlite_observed(held=time.perf_counter()-acquired,rollback=failed)


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
        if finished is not None:sqlite_observed(finish=time.perf_counter()-finished)
        end_write(acquired,failed=failed)


@contextmanager
def read_transaction(db):
    # The caller opens a query_only connection before entering this branch.
    # Its projection and pre-encoding still share an ordinary read snapshot.
    if db.execute('PRAGMA query_only').fetchone() != (1,):
        raise ValueError('Projection requires query-only connection')
    with db:
        db.execute('BEGIN')
        yield db
