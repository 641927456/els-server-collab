"""Lifetime reset quota, independent of transient bag rows and legacy JSON.

The single row is retained after consumption/expiry as an anti-reuse tombstone.
Container moves and same-UID manufacture must not refund a lifetime reset.
Quota reader/primitive only; the separately guarded reset transaction owns effects.
"""
from els_server.domain.equipment_chip_rules import TEMPLATE,state

def exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_chip_reset_history'").fetchone() is not None

def used(db,uid):
    if type(uid) is not int or not 0<uid<2**63:raise ValueError('Chip reset UID')
    row=db.execute('SELECT used FROM equipment_chip_reset_history WHERE item_uid=?',(uid,)).fetchone() if exists(db) else None
    value=row[0] if row else 0
    if type(value) is not int or not 0<=value<=3:raise ValueError('Chip reset history bounds')
    return value

def hydrate(db,item):
    if item['template']!=TEMPLATE:return item
    values=state(TEMPLATE,item.get('chip_tuning',[0,0,0,0]));count=used(db,item['uid'])
    # Zero is the persisted legacy-compatible byte, never a quota refund.
    if values[3] not in (0,count):raise ValueError('Unbacked chip reset count')
    if count or 'chip_tuning' in item:return dict(item,chip_tuning=[*values[:3],count])
    return item

def legacy(item):
    if item.get('template')!=TEMPLATE or 'chip_tuning' not in item:return item
    values=state(TEMPLATE,item['chip_tuning'])
    return dict(item,chip_tuning=[*values[:3],0])

def record(db,owner,uid,expected):
    """Caller owns the atomic user-local reset transaction."""
    if not db.in_transaction:raise ValueError('Chip reset history requires transaction')
    if type(expected) is not int or not 0<=expected<3:raise ValueError('Chip reset quota exhausted or invalid')
    row=db.execute('SELECT template,count FROM inventory_items WHERE uid=? AND owner=?',(uid,owner)).fetchone()
    if row!=(TEMPLATE,1):raise ValueError('Owned single chip reset history required')
    if used(db,uid)!=expected:raise ValueError('Stale chip reset history')
    db.execute("""CREATE TABLE IF NOT EXISTS equipment_chip_reset_history (
        item_uid INTEGER PRIMARY KEY CHECK(item_uid>0),
        used INTEGER NOT NULL CHECK(typeof(used)='integer' AND used BETWEEN 1 AND 3))""")
    if expected:
        if db.execute('UPDATE equipment_chip_reset_history SET used=? WHERE item_uid=? AND used=?',(expected+1,uid,expected)).rowcount!=1:raise ValueError('Stale chip reset history update')
    else:db.execute('INSERT INTO equipment_chip_reset_history VALUES (?,1)',(uid,))
    return expected+1
