"""Read-only source generation retained without retaining a SQL transaction.

The same observer connection supplies both data_version tokens. Opening a new
connection for validation would make the comparison meaningless. A changed
token invalidates the result; it never authorizes reuse of another owner's data.
"""
from pathlib import Path
import sqlite3
import threading


class SourceChanged(ValueError):
    pass


class SnapshotLease:
    def __init__(self, path, db, file_id, version):
        self._path, self._db = path, db
        self._file_id, self._version = file_id, version
        self._lock = threading.Lock()

    def current(self):
        """Nonblocking SQLite check. Called under the session operation lock."""
        with self._lock:
            if self._db is None:
                return False
            try:
                before = _identity(self._path)
                version = self._db.execute('PRAGMA data_version').fetchone()[0]
                return (before == self._file_id == _identity(self._path)
                        and version == self._version and not self._db.in_transaction)
            except (OSError, sqlite3.Error):
                return False

    def close(self):
        with self._lock:
            db, self._db = self._db, None
            if db is not None:
                db.close()


def _identity(path):
    value = path.stat()
    return value.st_dev, value.st_ino


def capture(path, owner, account_id, *, at=None):
    """Capture one generation; fail on concurrent commit instead of mixing it.

    Query-only also rejects accidental schema/lazy writers in source readers.
    A successful caller owns the lease and must close it on every exit. All
    expensive arithmetic must occur after this function has rolled back BEGIN.
    """
    from els_server.storage.native_attribute_snapshot import read_in_transaction
    path = Path(path).resolve(strict=True)
    file_id = _identity(path)
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                         isolation_level=None, timeout=0, check_same_thread=False)
    try:
        db.execute('PRAGMA query_only=ON')
        before = db.execute('PRAGMA data_version').fetchone()[0]
        db.execute('BEGIN')
        try:
            value = read_in_transaction(db, owner, account_id, at=at)
        finally:
            db.rollback()
        after = db.execute('PRAGMA data_version').fetchone()[0]
        if before != after or file_id != _identity(path):
            raise SourceChanged('Native attribute source changed during capture')
        return value, SnapshotLease(path, db, file_id, after)
    except BaseException:
        db.close()
        raise
