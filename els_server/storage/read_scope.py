"""Reuse committed role projections only inside one serialized operation.

The read-only observer connection never writes or holds a read transaction.
SQLite data_version changes when ANY other connection commits to that file,
including the ordinary writers used by the current operation. No TTL or
process-wide role snapshot is used; ownership and enabled-account checks are
still performed by their existing consumers.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
import sqlite3
import threading


_current = ContextVar('committed_role_read_scope', default=None)


class _ReadScope:
    def __init__(self):
        self.thread = threading.get_ident()
        self.connections = {}
        self.values = {}

    def read(self, path, key, load):
        path = Path(path).resolve()
        observer = self.connections.get(path)
        if observer is None:
            observer = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                       isolation_level=None, timeout=10)
            self.connections[path] = observer
        before = observer.execute('PRAGMA data_version').fetchone()[0]
        identity = (path, key)
        saved = self.values.get(identity)
        if saved is not None and saved[0] == before:
            return deepcopy(saved[1])
        value = load()
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
            for connection in self.connections.values():
                connection.close()
        finally:
            self.connections.clear()
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
