"""Account-owned native 397/398 keyboard preferences, restored by 399.

The client owns defaults and key actions. Old per-character rows remain intact;
before the first account save, the lowest owned UID supplies compatibility data.
Accounts with no saved keys receive the same-version native default map.
Existing nonempty account/legacy preferences and all stored rows stay intact.
"""
import sqlite3
import struct
from contextlib import closing
from pathlib import Path
from els_server.domain.key_bindings import DEFAULT_BINDINGS,validate_bindings


# 6c6b5180 native482D90 defaults, translated by3FFA290. Offline native
# replay matches the untouched client first397 byte for byte (85 actions).
# Complete maps take native399 restore; empty maps take a different reset path
# whose first-tutorial exit leaves the HUD key labels empty.
_NATIVE_DEFAULT_CODES = (43, 44, 30, 31, 32, 45, 33, 16, 17, 18, 19, 20, 57, 26, 27, 13, 12, 38, 49, 11, 22, 23, 24, 25, 47, 37, 48, 21, 55, 2, 3, 4, 5, 6, 7, 54, 61, 60, 62, 46, 34, 35, 81, 36, 40, 50, 82, 53, 29, 1, 83, -1, -1, -1, 10, 42, 84, 85, 86, 87, -1, -1, -1, -1, -1, 88, 89, 90, 56, 28, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 80, 101, 58, 102, 103)
_NATIVE_DEFAULT_BINDINGS = (struct.pack('>I',85)
    + b''.join(struct.pack('>hh',i,v) for i,v in enumerate(_NATIVE_DEFAULT_CODES))
    + bytes(8))

def _restore(payload):
    payload=validate_bindings(payload)
    return _NATIVE_DEFAULT_BINDINGS if payload==DEFAULT_BINDINGS else payload


def account_identity(value):
    if type(value) is not int or not 1<=value<2**63:
        raise ValueError('Invalid key binding account')
    return value


def _table(db,name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None


def _load(db,account_id):
    if _table(db,'account_key_bindings'):
        row=db.execute('SELECT payload FROM account_key_bindings WHERE account_id=?',(account_id,)).fetchone()
        if row is not None:return _restore(row[0])
    # A legacy save may contain several character-local preferences. Preserve
    # every row; use the first owned character only until a native 397 selects
    # the authoritative account preference. Never fall back to global UID1001.
    if _table(db,'key_bindings') and _table(db,'character_owners'):
        row=db.execute('SELECT k.payload FROM key_bindings k JOIN character_owners o ON o.uid=k.uid WHERE o.account_id=? ORDER BY k.uid LIMIT 1',(account_id,)).fetchone()
        if row is not None:return _restore(row[0])
    return _NATIVE_DEFAULT_BINDINGS


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
