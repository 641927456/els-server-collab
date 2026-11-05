"""Attribute persistence joined by item UID; writes share the caller transaction."""
from els_server.storage.character_schema import character_uid
from els_server.domain.equipment_attributes import validate_slots


def ensure_attributes(db):
    db.execute('''CREATE TABLE IF NOT EXISTS equipment_attributes (
        item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,
        slot0 INTEGER NOT NULL CHECK(slot0 BETWEEN 0 AND 6),
        slot1 INTEGER NOT NULL CHECK(slot1 BETWEEN 0 AND 6),
        slot2 INTEGER NOT NULL CHECK(slot2 BETWEEN 0 AND 6),
        slot3 INTEGER NOT NULL CHECK(slot3 BETWEEN 0 AND 6))''')


def attach_attributes(db,items,owner):
    # A read-only snapshot of older saves must not cause an implicit migration.
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_attributes'").fetchone():return items
    owned={i['uid']:i for i in items}
    if not owned:return items
    # Join the current ownership set, not a receipt's historical item owner.
    for row in db.execute('''SELECT a.item_uid,a.slot0,a.slot1,a.slot2,a.slot3
        FROM equipment_attributes a JOIN inventory_items i ON i.uid=a.item_uid WHERE i.owner=?''',(owner,)):
        item=owned.get(row[0])
        if item is not None:item['attributes']=validate_slots(item['template'],row[1:])
    return items


def replace_attributes(db,owner,item_uid,expected,updated):
    """Internal compare-and-set primitive, not a free enchanting endpoint."""
    if not db.in_transaction:raise ValueError('Attribute update requires an explicit transaction')
    owner=character_uid(owner)
    if type(item_uid) is not int or not 1<=item_uid<2**63:raise ValueError('Item UID')
    item=db.execute('SELECT template,count FROM inventory_items WHERE uid=? AND owner=?',(item_uid,owner)).fetchone()
    if item is None or item[1]!=1:raise ValueError('Owned single equipment required')
    expected=validate_slots(item[0],expected);updated=validate_slots(item[0],updated)
    ensure_attributes(db)
    previous=db.execute('SELECT slot0,slot1,slot2,slot3 FROM equipment_attributes WHERE item_uid=?',(item_uid,)).fetchone()
    if list(previous or (0,0,0,0))!=expected:raise ValueError('Stale equipment attributes')
    if any(updated):
        db.execute('''INSERT INTO equipment_attributes VALUES (?,?,?,?,?)
            ON CONFLICT(item_uid) DO UPDATE SET slot0=excluded.slot0,slot1=excluded.slot1,slot2=excluded.slot2,slot3=excluded.slot3''',(item_uid,*updated))
    else:db.execute('DELETE FROM equipment_attributes WHERE item_uid=?',(item_uid,))
    return list(updated)
