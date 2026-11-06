"""Per-character native guidebook flags; existing saves start unread."""
from els_server.storage.item_actor import require_active_character


def actor(db,store,account_id):
    require_active_character(db,store.uid)
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(store.uid,)).fetchone()!=(account_id,):
        raise ValueError('Guidebook character owner mismatch')


def exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='guidebook_flags'").fetchone() is not None


def load(store,account_id):
    with store.connect() as db:
        db.execute('BEGIN')
        actor(db,store,account_id)
        if not exists(db):return {}
        return dict(db.execute('SELECT flag,opened FROM guidebook_flags WHERE uid=? ORDER BY flag',(store.uid,)))


def save(store,account_id,flags):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        actor(db,store,account_id)
        db.execute('''CREATE TABLE IF NOT EXISTS guidebook_flags (
            uid INTEGER NOT NULL REFERENCES characters(uid),
            flag INTEGER NOT NULL CHECK(flag BETWEEN 1 AND 2147483647),
            opened INTEGER NOT NULL CHECK(opened IN (0,1)),
            PRIMARY KEY(uid,flag))''')
        # 89D720 uploads the entire map, including explicit false entries.
        db.execute('DELETE FROM guidebook_flags WHERE uid=?',(store.uid,))
        db.executemany('INSERT INTO guidebook_flags VALUES (?,?,?)',
                       ((store.uid,index,opened) for index,opened in flags.items()))
