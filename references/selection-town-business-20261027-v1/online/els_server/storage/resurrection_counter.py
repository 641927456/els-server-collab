"""Readonly known-source role counter; absence is0, never a free grant."""
from contextlib import closing
from pathlib import Path
import sqlite3
from els_server.storage.character_schema import character_uid
MAX_COUNT=2**31-1

def validate_count(value):
    if type(value) is not int or not 0<=value<=MAX_COUNT:raise ValueError('Invalid known resurrection counter')
    return value

def count(db,owner):
    owner=character_uid(owner)
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='known_resurrection_stones'").fetchone()
    row=db.execute('SELECT count FROM known_resurrection_stones WHERE owner=?',(owner,)).fetchone() if exists else None
    return validate_count(row[0] if row else 0)

def snapshot(path,owner):
    with snapshot_connection(path) as db:
        return count(db,owner)

from els_server.storage.read_scope import snapshot_connection
