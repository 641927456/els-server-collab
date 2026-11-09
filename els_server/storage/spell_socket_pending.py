"""Paid previews; lazy exact8-to12 material check upgrade in original writer."""
import json
TABLE='equipment_spell_pending'
COLUMNS=('owner','item_uid','generation','socket_group','slot','option_id','material_id','source_uid','basis_json','created_at')


OLD_SQL="CREATE TABLE equipment_spell_pending (\n      owner INTEGER PRIMARY KEY REFERENCES characters(uid) CHECK(typeof(owner)='integer' AND owner>=1001),\n      item_uid INTEGER NOT NULL REFERENCES inventory_items(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED CHECK(typeof(item_uid)='integer' AND item_uid>0),\n      generation TEXT NOT NULL UNIQUE CHECK(typeof(generation)='text' AND length(generation) BETWEEN 1 AND 160),\n      socket_group INTEGER NOT NULL CHECK(typeof(socket_group)='integer' AND socket_group IN (9,10,11,12)),\n      slot INTEGER NOT NULL CHECK(typeof(slot)='integer' AND slot>=0 AND slot<CASE WHEN socket_group=12 THEN 3 ELSE 9 END),\n      option_id INTEGER NOT NULL CHECK(typeof(option_id)='integer' AND option_id>0 AND option_id<2147483648),\n      material_id INTEGER NOT NULL CHECK(typeof(material_id)='integer' AND material_id IN (135877,135880,135883,135886,136109,136110,136111,136112)),\n      source_uid INTEGER NOT NULL CHECK(typeof(source_uid)='integer' AND source_uid>0 AND source_uid!=item_uid),\n      basis_json TEXT NOT NULL CHECK(typeof(basis_json)='text' AND length(basis_json) BETWEEN 1 AND 65536),\n      created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0))"
NEW_SQL="CREATE TABLE equipment_spell_pending (\n      owner INTEGER PRIMARY KEY REFERENCES characters(uid) CHECK(typeof(owner)='integer' AND owner>=1001),\n      item_uid INTEGER NOT NULL REFERENCES inventory_items(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED CHECK(typeof(item_uid)='integer' AND item_uid>0),\n      generation TEXT NOT NULL UNIQUE CHECK(typeof(generation)='text' AND length(generation) BETWEEN 1 AND 160),\n      socket_group INTEGER NOT NULL CHECK(typeof(socket_group)='integer' AND socket_group IN (9,10,11,12)),\n      slot INTEGER NOT NULL CHECK(typeof(slot)='integer' AND slot>=0 AND slot<CASE WHEN socket_group=12 THEN 3 ELSE 9 END),\n      option_id INTEGER NOT NULL CHECK(typeof(option_id)='integer' AND option_id>0 AND option_id<2147483648),\n      material_id INTEGER NOT NULL CHECK(typeof(material_id)='integer' AND material_id IN (135877,135880,135883,135886,136109,136110,136111,136112,135879,135882,135885,135888)),\n      source_uid INTEGER NOT NULL CHECK(typeof(source_uid)='integer' AND source_uid>0 AND source_uid!=item_uid),\n      basis_json TEXT NOT NULL CHECK(typeof(basis_json)='text' AND length(basis_json) BETWEEN 1 AND 65536),\n      created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0))"
UPGRADE_TABLE='equipment_spell_pending_upgrade'

def _normalized(sql):
 return ' '.join(sql.split()).replace('"equipment_spell_pending"','equipment_spell_pending').rstrip(';')

def layout(db):
 row=db.execute("SELECT type,sql FROM sqlite_master WHERE name=?",(TABLE,)).fetchone()
 if row is None:return None
 if row[0]!='table'or tuple(r[1]for r in db.execute('PRAGMA table_info(equipment_spell_pending)'))!=COLUMNS:raise ValueError('Unknown mystic pending schema')
 value=_normalized(row[1])
 if value==_normalized(NEW_SQL):return 2
 if value==_normalized(OLD_SQL):return 1
 raise ValueError('Unknown mystic pending constraints')

def present(db):return layout(db)is not None

def _upgrade(db):
 # Only the exact prior table can reach this path. Refuse unknown extensions.
 if db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(UPGRADE_TABLE,)).fetchone():raise ValueError('Mystic pending upgrade name occupied')
 indexes=db.execute('PRAGMA index_list(equipment_spell_pending)').fetchall()
 if(len(indexes)!=1 or indexes[0][2:]!=(1,'u',0)
    or tuple(r[2]for r in db.execute('PRAGMA index_info("'+indexes[0][1]+'")'))!=('generation',)
    or db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger'AND tbl_name=?",(TABLE,)).fetchone()):raise ValueError('Unknown mystic pending extensions')
 for(name,)in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
  safe=name.replace('"','""')
  if any(r[2]==TABLE for r in db.execute('PRAGMA foreign_key_list("'+safe+'")')):raise ValueError('Mystic pending referenced by unknown table')
 db.execute(NEW_SQL.replace('CREATE TABLE '+TABLE+' (','CREATE TABLE '+UPGRADE_TABLE+' (',1))
 names=','.join(COLUMNS)
 db.execute('INSERT INTO '+UPGRADE_TABLE+'('+names+')SELECT '+names+' FROM '+TABLE)
 if(db.execute('SELECT '+names+' FROM '+TABLE+' EXCEPT SELECT '+names+' FROM '+UPGRADE_TABLE).fetchone()
    or db.execute('SELECT '+names+' FROM '+UPGRADE_TABLE+' EXCEPT SELECT '+names+' FROM '+TABLE).fetchone()
    or db.execute('PRAGMA foreign_key_check('+UPGRADE_TABLE+')').fetchone()):raise ValueError('Mystic pending upgrade did not preserve rows')
 db.execute('DROP TABLE '+TABLE)
 db.execute('ALTER TABLE '+UPGRADE_TABLE+' RENAME TO '+TABLE)
 if layout(db)!=2:raise ValueError('Mystic pending upgrade final layout')

def ensure(db):
 if not db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Mystic pending requires original writer and FK')
 version=layout(db)
 if version==2:return
 if version==1:_upgrade(db)
 else:db.execute(NEW_SQL)

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
