"""Observe original SQLite writer boundaries, without changing retries or modes."""
from contextlib import contextmanager
import sqlite3
import time
from els_server.performance import sqlite_observed


@contextmanager
def write_transaction(db):
    # Keep an ordinary sqlite3.Connection, original BEGIN IMMEDIATE and the
    # original connection timeout. No wrapper type, pragma, retry or SQL text.
    started=time.perf_counter()
    try:db.execute('BEGIN IMMEDIATE')
    except BaseException as error:
        code=getattr(error,'sqlite_errorcode',None)
        sqlite_observed(wait=time.perf_counter()-started,
            busy=type(code) is int and code & 255 in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED))
        raise
    acquired=time.perf_counter();sqlite_observed(wait=acquired-started)
    failed=True
    try:
        with db:yield db
        failed=False
    finally:sqlite_observed(held=time.perf_counter()-acquired,rollback=failed)
