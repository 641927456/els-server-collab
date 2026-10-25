"""Optional paid-preview sidecar; reads and invalidation never install schema."""
import json
TABLE='equipment_spell_pending'
COLUMNS=('owner','item_uid','generation','socket_group','slot','option_id','material_id','source_uid','basis_json','created_at')

def present(db):
    row=db.execute("SELECT type FROM sqlite_master WHERE name=?",(TABLE,)).fetchone()
    if row is None:return False
    if row!=('table',)or tuple(r[1]for r in db.execute('PRAGMA table_info(equipment_spell_pending)'))!=COLUMNS:
        raise ValueError('Unknown mystic pending schema')
    return True

def ensure(db):
    if not db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Mystic pending requires original writer and FK')
    if present(db):return
    db.execute('''CREATE TABLE equipment_spell_pending (
      owner INTEGER PRIMARY KEY REFERENCES characters(uid) CHECK(typeof(owner)='integer' AND owner>=1001),
      item_uid INTEGER NOT NULL REFERENCES inventory_items(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED CHECK(typeof(item_uid)='integer' AND item_uid>0),
      generation TEXT NOT NULL UNIQUE CHECK(typeof(generation)='text' AND length(generation) BETWEEN 1 AND 160),
      socket_group INTEGER NOT NULL CHECK(typeof(socket_group)='integer' AND socket_group IN (9,10,11,12)),
      slot INTEGER NOT NULL CHECK(typeof(slot)='integer' AND slot>=0 AND slot<CASE WHEN socket_group=12 THEN 3 ELSE 9 END),
      option_id INTEGER NOT NULL CHECK(typeof(option_id)='integer' AND option_id>0 AND option_id<2147483648),
      material_id INTEGER NOT NULL CHECK(typeof(material_id)='integer' AND material_id IN (135877,135880,135883,135886,136109,136110,136111,136112)),
      source_uid INTEGER NOT NULL CHECK(typeof(source_uid)='integer' AND source_uid>0 AND source_uid!=item_uid),
      basis_json TEXT NOT NULL CHECK(typeof(basis_json)='text' AND length(basis_json) BETWEEN 1 AND 65536),
      created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0))''')

def get(db,owner):
    if not present(db):return None
    row=db.execute('SELECT * FROM equipment_spell_pending WHERE owner=?',(owner,)).fetchone()
    return dict(zip(COLUMNS,row))if row is not None else None

def cancel(db,owner,uids):
    if not db.in_transaction:raise ValueError('Mystic cancellation requires transaction')
    if not present(db):return
    for uid in set(uids):db.execute('DELETE FROM equipment_spell_pending WHERE owner=? AND item_uid=?',(owner,uid))

def invalidate_moved(db,owner,before,after):
    from els_server.storage.market_conversion_pending import invalidate_moved as market_invalidate
    market_invalidate(db,owner,before,after)
    if not present(db):return
    before={i['uid']:(i['group'],i['slot'])for i in before if isinstance(i,dict)and {'uid','group','slot'}<=set(i)}
    after={i['uid']:(i['group'],i['slot'])for i in after if isinstance(i,dict)and {'uid','group','slot'}<=set(i)}
    cancel(db,owner,[uid for uid,pos in before.items()if after.get(uid)!=pos])

def basis(item):return json.dumps(item,sort_keys=True,separators=(',',':'))
