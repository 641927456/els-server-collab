"""Optional UID-owned lock state. Moving/wearing preserves the same lock."""
from els_server.storage.erp_support_quest_scope import exists as _table_exists
from els_server.domain.item_locks import validate, require_unlocked


def exists(db):
    return bool(_table_exists(db,'item_locks'))


def attach(db, items, owner,*,selected_only=False):
    if exists(db):
        owned = {i['uid']: i for i in items}
        query='SELECT l.item_uid,l.lock_until FROM item_locks l\n                JOIN inventory_items i ON i.uid=l.item_uid WHERE i.owner=?'
        parameters=(owner,)
        if selected_only:
            query+=' AND i.uid IN ('+','.join('?' for _ in owned)+')';parameters+=tuple(owned)
        for (uid, deadline) in db.execute(query,parameters):
            if uid in owned:owned[uid]['lock_until'] = validate(deadline)
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
