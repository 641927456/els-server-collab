"""Durability belongs to the owned UID and shares inventory transactions."""
from els_server.storage.character_schema import character_uid
from els_server.domain.equipment_durability import LEGACY_INITIAL_DURABILITY, maximum, validate


def ensure_durability(db):
    db.execute('''CREATE TABLE IF NOT EXISTS equipment_durability (
        item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,
        current INTEGER NOT NULL CHECK(current BETWEEN 0 AND 32767))''')


def attach_durability(db,items,owner):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_durability'").fetchone():
        owned = {item['uid']: item for item in items}
        for uid, current in db.execute('''SELECT d.item_uid,d.current FROM equipment_durability d
            JOIN inventory_items i ON i.uid=d.item_uid WHERE i.owner=?''', (owner,)):
            if uid in owned:
                owned[uid]['durability'] = validate(owned[uid]['template'], current)
    # These legacy bag items had no wear path. An explicit zero is a saved
    # value and takes precedence over the missing-row compatibility default.
    for item in items:
        legacy = LEGACY_INITIAL_DURABILITY.get(item['template'])
        if legacy and 'durability' not in item and (item['group'], item['metadata'], item['count']) == (legacy[0], 1, 1):
            item['durability'] = maximum(item['template'])
    return items


def replace_durability(db,owner,item_uid,expected,updated):
    """Internal compare-and-set; does not expose a free repair endpoint."""
    if not db.in_transaction:raise ValueError('Durability update requires explicit transaction')
    owner=character_uid(owner)
    if type(item_uid) is not int or not 1<=item_uid<2**63:raise ValueError('Item UID')
    row=db.execute('SELECT template,count FROM inventory_items WHERE uid=? AND owner=?',(item_uid,owner)).fetchone()
    if row is None or row[1]!=1:raise ValueError('Owned single equipment required')
    validate(row[0],expected);validate(row[0],updated);ensure_durability(db)
    old=db.execute('SELECT current FROM equipment_durability WHERE item_uid=?',(item_uid,)).fetchone()
    if (old[0] if old else 0)!=expected:raise ValueError('Stale equipment durability')
    db.execute('''INSERT INTO equipment_durability VALUES (?,?)
        ON CONFLICT(item_uid) DO UPDATE SET current=excluded.current''',(item_uid,updated))
    return updated
