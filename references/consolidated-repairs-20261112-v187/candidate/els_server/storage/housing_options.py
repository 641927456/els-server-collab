"""Owner-controlled native housing name and public visibility."""
from contextlib import closing
from pathlib import Path
import sqlite3
import hashlib
from els_server.storage.housing_access import owner

TABLE = 'character_housing_options'
SQL = ('CREATE TABLE character_housing_options ('
       'owner INTEGER PRIMARY KEY REFERENCES characters(uid),'
       'account_id INTEGER NOT NULL,name TEXT NOT NULL,'
       'public INTEGER NOT NULL CHECK(public IN (0,1)),'
       'revision INTEGER NOT NULL CHECK(revision>0))')


def snapshot(db, uid, account):
    owner(db, uid, account)
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is None:
        return dict(name='', public=False, revision=0)
    row = db.execute('SELECT account_id,name,public,revision FROM character_housing_options WHERE owner=?', (uid,)).fetchone()
    if row is None:
        return dict(name='', public=False, revision=0)
    if row[0] != account or type(row[1]) is not str or row[2] not in (0, 1) or type(row[3]) is not int or row[3] <= 0:
        raise ValueError('Housing option saved identity')
    return dict(name=row[1], public=bool(row[2]), revision=row[3])


def project(db, uid, account, value):
    row = snapshot(db, uid, account)
    value['0ba'], value['0ee'] = row['name'], row['public']
    return value


def public_owners(db):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is None:
        return []
    return [uid for uid, in db.execute('SELECT owner FROM character_housing_options WHERE public=1 ORDER BY owner')]


def save(db, uid, account, name, public, operation, payload):
    if not db.in_transaction:
        raise ValueError('Housing options require the original writer')
    current = snapshot(db, uid, account)
    db.execute('CREATE TABLE IF NOT EXISTS housing_option_receipts (operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,request_hash TEXT NOT NULL)')
    digest = hashlib.sha256(payload).hexdigest()
    previous = db.execute('SELECT owner,account_id,request_hash FROM housing_option_receipts WHERE operation_id=?', (operation,)).fetchone()
    if previous is not None:
        if previous != (uid, account, digest):
            raise ValueError('Housing option retry changed')
        return
    db.execute('INSERT INTO housing_option_receipts VALUES (?,?,?,?)', (operation, uid, account, digest))
    if current['name'] == name and current['public'] == public:
        return
    if current['revision'] >= 2**63-1:
        raise ValueError('Housing option revision bound')
    if current['revision'] == 0 and db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).fetchone() is None:
        db.execute(SQL)
    db.execute('INSERT INTO character_housing_options VALUES (?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET name=excluded.name,public=excluded.public,revision=excluded.revision',
               (uid, account, name, int(public), current['revision'] + 1))
