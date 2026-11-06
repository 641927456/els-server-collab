"""Optional UID-owned lock state. Moving/wearing preserves the same lock."""
from els_server.domain.item_locks import validate, require_unlocked


def exists(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_locks'").fetchone())


def attach(db, items, owner):
    if exists(db):
        owned = {i['uid']: i for i in items}
        for uid, deadline in db.execute('''SELECT l.item_uid,l.lock_until FROM item_locks l
                JOIN inventory_items i ON i.uid=l.item_uid WHERE i.owner=?''', (owner,)):
            owned[uid]['lock_until'] = validate(deadline)
    return items


def assign(db, owner, uid, deadline):
    if not db.in_transaction:
        raise ValueError('Item locking requires a transaction')
    validate(deadline)
    if not db.execute('SELECT 1 FROM inventory_items WHERE uid=? AND owner=?', (uid, owner)).fetchone():
        raise ValueError('Item lock owner mismatch')
    db.execute('''CREATE TABLE IF NOT EXISTS item_locks (
        item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,
        lock_until INTEGER NOT NULL CHECK(lock_until>0))''')
    db.execute('INSERT INTO item_locks VALUES (?,?) ON CONFLICT(item_uid) DO UPDATE SET lock_until=excluded.lock_until', (uid, deadline))


def require_uid_unlocked(db, uid):
    if exists(db):
        row = db.execute('SELECT lock_until FROM item_locks WHERE item_uid=?', (uid,)).fetchone()
        if row:
            require_unlocked({'lock_until': row[0]})


def forget(db, uid):
    if exists(db):
        db.execute('DELETE FROM item_locks WHERE item_uid=?', (uid,))
