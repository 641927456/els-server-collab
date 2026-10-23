"""Account-owned native 397/398 keyboard preferences, restored by 399.

The client owns defaults and key actions. Old per-character rows remain intact;
before the first account save, the lowest owned UID supplies compatibility data.
An account without characters has no legacy source and receives the empty maps.
"""
import sqlite3
from contextlib import closing
from pathlib import Path
from els_server.domain.key_bindings import DEFAULT_BINDINGS,validate_bindings


def account_identity(value):
    if type(value) is not int or not 1<=value<2**63:
        raise ValueError('Invalid key binding account')
    return value


def _table(db,name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None


def _load(db,account_id):
    if _table(db,'account_key_bindings'):
        row=db.execute('SELECT payload FROM account_key_bindings WHERE account_id=?',(account_id,)).fetchone()
        if row is not None:return validate_bindings(row[0])
    # A legacy save may contain several character-local preferences. Preserve
    # every row; use the first owned character only until a native 397 selects
    # the authoritative account preference. Never fall back to global UID1001.
    if _table(db,'key_bindings') and _table(db,'character_owners'):
        row=db.execute('SELECT k.payload FROM key_bindings k JOIN character_owners o ON o.uid=k.uid WHERE o.account_id=? ORDER BY k.uid LIMIT 1',(account_id,)).fetchone()
        if row is not None:return validate_bindings(row[0])
    return DEFAULT_BINDINGS


def load(path,account_id):
    account_id=account_identity(account_id)
    # A preference read cannot create an empty database. One snapshot covers
    # the schema check and its row, including a concurrent first397 save.
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db,db:
        db.execute('BEGIN')
        return _load(db,account_id)


def save(path,account_id,payload):
    account_id=account_identity(account_id);payload=validate_bindings(payload)
    try:
        with closing(sqlite3.connect(path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS account_key_bindings (account_id INTEGER PRIMARY KEY CHECK(account_id>0), payload BLOB NOT NULL, revision INTEGER NOT NULL CHECK(revision>0))')
            db.execute('INSERT INTO account_key_bindings VALUES (?,?,1) ON CONFLICT(account_id) DO UPDATE SET payload=excluded.payload, revision=revision+1 WHERE payload<>excluded.payload',(account_id,payload))
            return _load(db,account_id)
    except sqlite3.Error as error:
        # The session must release the native 398 wait with failure, never
        # acknowledge an in-memory preference that failed to reach storage.
        raise ValueError('Key binding persistence failed') from error
