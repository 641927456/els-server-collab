"""Optional UID-owned enhancement state; no public free-upgrade endpoint."""
from els_server.storage.character_schema import character_uid
from els_server.domain.equipment_enhancement import validate


def exists(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_enhancement'").fetchone())


def attach(db,items,owner):
    if not exists(db):return items
    owned={i['uid']:i for i in items}
    for uid,level in db.execute('''SELECT e.item_uid,e.level FROM equipment_enhancement e
        JOIN inventory_items i ON i.uid=e.item_uid WHERE i.owner=?''',(owner,)):
        if uid in owned:owned[uid]['enhancement']=validate(owned[uid]['template'],level)
    return items


def replace(db,owner,item_uid,expected,updated):
    """Internal transactional compare-and-set for grants and future paid business."""
    if not db.in_transaction:raise ValueError('Enhancement update requires explicit transaction')
    owner=character_uid(owner)
    if type(item_uid) is not int or not 1<=item_uid<2**63:raise ValueError('Item UID')
    row=db.execute('SELECT template,count FROM inventory_items WHERE uid=? AND owner=?',(item_uid,owner)).fetchone()
    if row is None or row[1]!=1:raise ValueError('Owned single normal equipment required')
    from els_server.storage.item_locks import require_uid_unlocked
    require_uid_unlocked(db,item_uid)
    validate(row[0],expected);validate(row[0],updated)
    from els_server.storage.item_expiration import exists as timed
    from els_server.domain.item_expiration import require_current
    if timed(db):
        deadline=db.execute('SELECT expires_at FROM item_expiration WHERE item_uid=?',(item_uid,)).fetchone()
        if deadline:require_current(dict(expires_at=deadline[0]))
    present=exists(db)
    previous=db.execute('SELECT level FROM equipment_enhancement WHERE item_uid=?',(item_uid,)).fetchone() if present else None
    if (previous[0] if previous else 0)!=expected:raise ValueError('Stale equipment enhancement')
    if expected==updated:return updated
    if updated:
        if present:
            schema=db.execute("SELECT sql FROM sqlite_master WHERE name='equipment_enhancement'").fetchone()[0]
            if 'BETWEEN -20 AND 20' not in schema:
                # Migrate the old positive-only CHECK inside the caller's
                # transaction. No inventory rows or player identities change.
                db.execute('''CREATE TABLE equipment_enhancement_signed (
                    item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,
                    level INTEGER NOT NULL CHECK(level BETWEEN -20 AND 20 AND level<>0))''')
                db.execute('INSERT INTO equipment_enhancement_signed SELECT * FROM equipment_enhancement')
                db.execute('DROP TABLE equipment_enhancement')
                db.execute('ALTER TABLE equipment_enhancement_signed RENAME TO equipment_enhancement')
        db.execute('''CREATE TABLE IF NOT EXISTS equipment_enhancement (
            item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,
            level INTEGER NOT NULL CHECK(level BETWEEN -20 AND 20 AND level<>0))''')
        db.execute('''INSERT INTO equipment_enhancement VALUES (?,?)
            ON CONFLICT(item_uid) DO UPDATE SET level=excluded.level''',(item_uid,updated))
    elif present:db.execute('DELETE FROM equipment_enhancement WHERE item_uid=?',(item_uid,))
    return updated
