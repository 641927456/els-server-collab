"""Reuse committed role projections only inside one serialized operation.

The read-only observer connection never writes or holds a read transaction.
SQLite data_version changes when ANY other connection commits to that file,
including the ordinary writers used by the current operation. No TTL or
process-wide role snapshot is used; ownership and enabled-account checks are
still performed by their existing consumers.
"""
from contextlib import contextmanager,closing
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import sqlite3
import threading
import time
from els_server.performance import projection_loaded


_current = ContextVar('committed_role_read_scope', default=None)


class _ReadScope:
    def __init__(self):
        self.thread = threading.get_ident()
        self.connections = {}
        self.files = {}
        self.readers = {}
        self.values = {}

    def read(self, path, key, load):
        path = Path(path).resolve()
        stat = path.stat(); file_id = (stat.st_dev, stat.st_ino)
        if self.files.get(path) not in (None,file_id):
            observer=self.connections.pop(path,None)
            if observer is not None:observer.close()
            reader=self.readers.pop(path,None)
            if reader is not None:reader.close()
            self.values = {key:value for key,value in self.values.items() if key[0] != path}
        self.files[path] = file_id
        observer = self.connections.get(path)
        if observer is None:
            observer = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                       isolation_level=None, timeout=10)
            self.connections[path] = observer
        before = observer.execute('PRAGMA data_version').fetchone()[0]
        identity = (path, key)
        saved = self.values.get(identity)
        if saved is not None and saved[0] == before:
            projection_loaded(0,hit=True)
            return deepcopy(saved[1])
        started=time.perf_counter()
        try:
            value = load()
        finally:
            projection_loaded(time.perf_counter()-started)
        after = observer.execute('PRAGMA data_version').fetchone()[0]
        # A writer may commit between any two component reads. Return the
        # existing consumer's result, but do not reuse a mixed-version view.
        if before == after:
            self.values[identity] = (after, deepcopy(value))
        else:
            self.values.pop(identity, None)
        return value

    def close(self):
        try:
            for connection in (*self.connections.values(),*self.readers.values()):
                connection.close()
        finally:
            self.connections.clear()
            self.files.clear()
            self.readers.clear()
            self.values.clear()


@contextmanager
def committed_reads():
    current = _current.get()
    if current is not None and current.thread == threading.get_ident():
        yield
        return
    scope = _ReadScope()
    token = _current.set(scope)
    try:
        yield
    finally:
        try:
            scope.close()
        finally:
            _current.reset(token)


def role_projection(account, load, *, projection='full'):
    scope = _current.get()
    if (scope is None or scope.thread != threading.get_ident()
            or account.characters is None or account.store is None):
        return load()
    return scope.read(account.store.path,
                      (account.account_id, account.uid, id(account.characters), projection), load)


def inventory_projection(account,inventory,load):
    """Reuse only within an operation and a committed SQL/file generation.

    The caller still performs inventory initialization and legacy circuit
    repair before each access. No authentication, owner or live lease cache.
    A second boundary prevents time-derived validation from crossing expiry.
    """
    scope=_current.get();store=getattr(account,'store',None)
    if (scope is None or scope.thread != threading.get_ident()
            or getattr(account,'characters',None) is None or store is None
            or store.uid != account.uid or inventory.uid != account.uid
            or Path(store.path).resolve() != Path(inventory.path).resolve()):
        return load()
    return scope.read(store.path,('inventory',account.account_id,account.uid,
        id(store),id(inventory),int(time.time())),load)



@contextmanager
def snapshot_connection(path):
    """Operation-local read-only connection; no read transaction may escape.

    Used only by explicit snapshot/identity readers. A nested reader receives
    a separate connection, preserving the original independent transaction.
    """
    path=Path(path).resolve();scope=_current.get()
    if scope is None or scope.thread != threading.get_ident():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=10)) as db:
            try:yield db
            finally:
                if db.in_transaction:db.rollback()
        return
    # Reuse the observer's generation check without borrowing any data value.
    stat=path.stat();identity=(stat.st_dev,stat.st_ino)
    if scope.files.get(path)!=identity:
        for connections in (scope.connections,scope.readers):
            old=connections.pop(path,None)
            if old is not None:old.close()
        scope.values={key:value for key,value in scope.values.items() if key[0]!=path}
        scope.files[path]=identity
    db=scope.readers.get(path)
    if db is not None and db.in_transaction:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=10)) as nested:
            try:yield nested
            finally:
                if nested.in_transaction:nested.rollback()
        return
    if db is None:
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=10)
        scope.readers[path]=db
    try:yield db
    finally:
        if db.in_transaction:db.rollback()
