"""Keep a festival visit's source in the same transaction as its location."""
from els_server.storage.local_state import TOWN_SCENES

FESTIVAL_TOWN=1503


def _exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='festival_return_origins'").fetchone() is not None


def transition(db,uid,source,destination):
    if source==destination:return
    if destination==FESTIVAL_TOWN:
        if source not in TOWN_SCENES:raise ValueError('Festival source is not a town')
        owner=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
        if owner is None:raise ValueError('Festival source character owner')
        db.execute('CREATE TABLE IF NOT EXISTS festival_return_origins (uid INTEGER PRIMARY KEY REFERENCES characters(uid) ON DELETE CASCADE, account_id INTEGER NOT NULL, town INTEGER NOT NULL CHECK(town<>1503))')
        db.execute('INSERT INTO festival_return_origins VALUES (?,?,?) ON CONFLICT(uid) DO UPDATE SET account_id=excluded.account_id,town=excluded.town',(uid,owner[0],source))
    elif source==FESTIVAL_TOWN and _exists(db):
        db.execute('DELETE FROM festival_return_origins WHERE uid=?',(uid,))


def saved(db,uid,account_id):
    if not _exists(db):return None
    row=db.execute('SELECT f.town FROM festival_return_origins f JOIN character_owners o ON o.uid=f.uid AND o.account_id=f.account_id JOIN location l ON l.uid=f.uid WHERE f.uid=? AND f.account_id=? AND l.town=1503',(uid,account_id)).fetchone()
    if row is None:return None
    if row[0] not in TOWN_SCENES or row[0]==FESTIVAL_TOWN:raise ValueError('Invalid festival saved source')
    return row[0]
