"""Character-owned original social choices; unsaved reads never create rows."""
from contextlib import closing
from pathlib import Path
import sqlite3
from els_server.protocol.social_settings_messages import DEFAULT,validate,reply
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character

TABLE='native_social_settings'
SQL='CREATE TABLE native_social_settings (owner INTEGER PRIMARY KEY REFERENCES characters(uid),payload BLOB NOT NULL CHECK(length(payload)=10),revision INTEGER NOT NULL CHECK(revision>0))'

def snapshot(db,owner,account):
    require_owner(db,owner,account)
    schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()
    if schema is None:return DEFAULT
    if schema!=(SQL,):raise ValueError('Unknown native social settings schema')
    row=db.execute('SELECT payload,revision FROM native_social_settings WHERE owner=?',(owner,)).fetchone()
    if row is None:return DEFAULT
    if type(row[1])is not int or row[1]<1:raise ValueError('Native social settings revision')
    return validate(row[0])

def load(path,owner,account):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
        db.execute('BEGIN')
        return snapshot(db,owner,account)

def save(path,owner,account,payload,guard):
    payload=validate(payload)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_active_character(db,owner)
        before=snapshot(db,owner,account)
        if before!=payload:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone():db.execute(SQL)
            db.execute('INSERT INTO native_social_settings VALUES(?,?,1)ON CONFLICT(owner)DO UPDATE SET payload=excluded.payload,revision=revision+1 WHERE payload<>excluded.payload',(owner,payload))
        answer=[reply(payload)]
        for event in answer:encode_event(event)
        guard(db);require_active_character(db,owner)
        if snapshot(db,owner,account)!=payload:raise ValueError('Native social settings changed before commit')
        return answer
