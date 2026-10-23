"""Finite account-shared singleton D4E, current-state retries and readonly D4D.

The credential database is never attached or modified. All state and both
receipts share the inventory database transaction. No migration or equip route.
"""
from contextlib import closing
from pathlib import Path
import json,sqlite3,time
from els_server.domain.cartridge_registration_rules import POLICY,account_state,source
from els_server.protocol.equipment_cartridge_messages import request,acknowledge
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.domain.inventory_items import validate_item

SCHEMAS={
 'account_cartridge_state':'''CREATE TABLE account_cartridge_state (
 account_id INTEGER PRIMARY KEY CHECK(typeof(account_id)='integer' AND account_id>0),
 points INTEGER NOT NULL CHECK(typeof(points)='integer' AND points BETWEEN 0 AND 50000),
 revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision BETWEEN 0 AND 9223372036854775807))''',
 'account_cartridge_collection':'''CREATE TABLE account_cartridge_collection (
 account_id INTEGER NOT NULL REFERENCES account_cartridge_state(account_id),
 cartridge_id INTEGER NOT NULL CHECK(typeof(cartridge_id)='integer' AND cartridge_id BETWEEN 1 AND 19),
 level INTEGER NOT NULL CHECK(typeof(level)='integer' AND level BETWEEN 1 AND 6),
 bound_uid INTEGER NOT NULL CHECK(typeof(bound_uid)='integer' AND bound_uid=0),
 PRIMARY KEY(account_id,cartridge_id))''',
 'account_cartridge_registration_receipts':'''CREATE TABLE account_cartridge_registration_receipts (
 operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
 account_id INTEGER NOT NULL REFERENCES account_cartridge_state(account_id),
 actor_uid INTEGER NOT NULL CHECK(typeof(actor_uid)='integer' AND actor_uid>=1001),
 source_uid INTEGER NOT NULL CHECK(typeof(source_uid)='integer' AND source_uid>0),
 source_template INTEGER NOT NULL, cartridge_id INTEGER NOT NULL,
 response_id INTEGER NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
 policy_id TEXT NOT NULL)'''
}
LEGACY=('equipment_cartridge_states','equipment_cartridge_points')


def _authority(db,owner,account_id,authorize):
 if not db.in_transaction:raise ValueError('Cartridge transaction required')
 require_active_character(db,owner);require_owner(db,owner,account_id)
 if authorize is not None and not authorize():raise ValueError('Obsolete Cartridge session')


def _schema(db,*,create=False):
 # No qualified legacy role schema exists: presence needs separate review.
 # Read metadata only; never inspect unrelated players' historical rows.
 for name in LEGACY:
  if db.execute("SELECT 1 FROM sqlite_master WHERE name=? COLLATE NOCASE",(name,)).fetchone():
   raise ValueError('Cartridge legacy role history requires independent review')
 found={name:db.execute("SELECT type,sql FROM sqlite_master WHERE name=? COLLATE NOCASE",(name,)).fetchall()for name in SCHEMAS}
 for rows in found.values():
  if rows and (len(rows)!=1 or rows[0][0]!='table'):raise ValueError('Unknown Cartridge schema object collision')
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND lower(tbl_name) IN (?,?,?) LIMIT 1",tuple(SCHEMAS)).fetchone():raise ValueError('Unknown associated Cartridge trigger')
 if not any(found.values()):
  if not create:return False
  if db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Cartridge schema foreign keys required')
  for sql in SCHEMAS.values():db.execute(sql)
  return True
 if not all(found.values()):raise ValueError('Partial Cartridge account schema')
 for name,rows in found.items():
  if ' '.join(rows[0][1].split())!=' '.join(SCHEMAS[name].split()):raise ValueError('Unknown Cartridge account schema')
 return True


def _raw_json(raw):
 def unique(pairs):
  out={}
  for key,value in pairs:
   if key in out:raise ValueError('Duplicate persisted Cartridge inspection key')
   out[key]=value
  return out
 try:return json.loads(raw,object_pairs_hook=unique)
 except (TypeError,json.JSONDecodeError)as exc:raise ValueError('Malformed persisted Cartridge inspection JSON')from exc


def _groups_guard(groups):
 if type(groups)is not dict:raise ValueError('Unknown persisted option groups')
 for key,rows in groups.items():
  if (type(key)is not str or not key.isdecimal() or str(int(key))!=key
      or type(rows)is not list):
   raise ValueError('Malformed persisted option group')
  # Vector32 is unqualified here, NOT identified as Cartridge's native scalar.
  if key=='32':raise ValueError('Unknown persisted vector32 requires independent review')


def _legacy_guard(db,account_id,has_schema):
 """Inspect this account's raw containers BEFORE empty D4D or new registration.

 load_items cannot prove absence: its current sage validator rejects group32.
 No extraction, migration, deletion or inferred collection is performed here.
 """
 exists=lambda name:bool(db.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'",(name,)).fetchone())
 if exists('equipment_options'):
  for raw, in db.execute('SELECT e.groups_json FROM equipment_options e JOIN inventory_items i ON i.uid=e.item_uid JOIN character_owners o ON o.uid=i.owner WHERE o.account_id=?',(account_id,)):
   _groups_guard(_raw_json(raw))
 for table,query in (
  ('private_bank_items','SELECT b.item_json FROM private_bank_items b JOIN character_owners o ON o.uid=b.owner WHERE o.account_id=?'),
  ('shared_bank_items','SELECT item_json FROM shared_bank_items WHERE account_id=?')):
  if exists(table):
   for raw, in db.execute(query,(account_id,)):
    item=_raw_json(raw)
    if type(item)is not dict or 'cartridge'in item:raise ValueError('Unknown bank Cartridge state')
    _groups_guard(item.get('option_groups',{}))
 if exists('inventory_action_receipts'):
  # The three other successful routes are not part of this finite schema.
  if db.execute('SELECT 1 FROM inventory_action_receipts r JOIN character_owners o ON o.uid=r.owner WHERE o.account_id=? AND r.kind IN (?,?,?) LIMIT 1',(account_id,0xd50,0xd52,0xd54)).fetchone():raise ValueError('Unqualified Cartridge operation history')
  paired='NOT EXISTS (SELECT 1 FROM account_cartridge_registration_receipts a WHERE a.operation_id=r.operation_id AND a.account_id=? AND a.actor_uid=r.owner AND a.request_hash=r.request_hash)'if has_schema else '1'
  args=(account_id,0xd4e,account_id)if has_schema else(account_id,0xd4e)
  if db.execute('SELECT 1 FROM inventory_action_receipts r JOIN character_owners o ON o.uid=r.owner WHERE o.account_id=? AND r.kind=? AND '+paired+' LIMIT 1',args).fetchone():raise ValueError('Orphan Cartridge inventory receipt')
 if has_schema:
  if not exists('inventory_action_receipts'):
   if db.execute('SELECT 1 FROM account_cartridge_registration_receipts WHERE account_id=? LIMIT 1',(account_id,)).fetchone():raise ValueError('Orphan Cartridge account receipt')
  elif db.execute('SELECT 1 FROM account_cartridge_registration_receipts a WHERE a.account_id=? AND NOT EXISTS (SELECT 1 FROM inventory_action_receipts r WHERE r.operation_id=a.operation_id AND r.owner=a.actor_uid AND r.kind=? AND r.request_hash=a.request_hash) LIMIT 1',(account_id,0xd4e)).fetchone():raise ValueError('Unpaired Cartridge account receipt')


def _read(db,account_id):
 has_schema=_schema(db);_legacy_guard(db,account_id,has_schema)
 if not has_schema:return account_state({},0,0)
 row=db.execute('SELECT points,revision FROM account_cartridge_state WHERE account_id=?',(account_id,)).fetchone()
 raw=db.execute('SELECT cartridge_id,bound_uid,level FROM account_cartridge_collection WHERE account_id=? ORDER BY cartridge_id',(account_id,)).fetchall()
 if row is None:
  if raw or db.execute('SELECT 1 FROM account_cartridge_registration_receipts WHERE account_id=?',(account_id,)).fetchone():raise ValueError('Orphan Cartridge account data')
  return account_state({},0,0)
 if not raw or row[1]<1:raise ValueError('Invalid persisted Cartridge account record')
 rows={i:(u,l)for i,u,l in raw}
 if len(rows)!=len(raw):raise ValueError('Duplicate Cartridge account ID')
 return account_state(rows,*row)


def snapshot(path,owner,account_id,*,authorize=None):
 """One readonly SQLite version for account rows, points and revision; no DDL."""
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
  db.execute('BEGIN');_authority(db,owner,account_id,authorize)
  value=_read(db,account_id)
  if authorize is not None and not authorize():raise ValueError('Obsolete Cartridge snapshot')
  return dict(value,account_id=account_id)


def _packed(value):
 return dict(rows=[[i,*value['rows'][i]]for i in sorted(value['rows'])],points=value['points'],revision=value['revision'])


def _unpacked(raw):
 value=_raw_json(raw)
 if type(value)is not dict or set(value)!={'rows','points','revision'}or type(value['rows'])is not list:raise ValueError('Cartridge receipt account shape')
 rows={}
 for r in value['rows']:
  if type(r)is not list or len(r)!=3 or r[0]in rows:raise ValueError('Cartridge receipt account rows')
  rows[r[0]]=tuple(r[1:])
 out=account_state(rows,value['points'],value['revision'])
 if not rows and (out['points']or out['revision']):raise ValueError('Cartridge receipt empty account')
 return out


def _history(db,operation,digest,owner,account_id,item_uid,positions):
 if not _schema(db):raise ValueError('Cartridge account receipt missing')
 row=db.execute('SELECT request_hash,account_id,actor_uid,source_uid,source_template,cartridge_id,response_id,before_json,after_json,policy_id FROM account_cartridge_registration_receipts WHERE operation_id=?',(operation,)).fetchone()
 generic=db.execute('SELECT owner,kind,request_hash,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
 if (row is None or generic is None or row[:4]!=(digest,account_id,owner,item_uid)
     or row[9]!=POLICY or generic[:3]!=(owner,0xd4e,digest)):
  raise ValueError('Cartridge paired receipt identity')
 try:
  before_items,after_items=_raw_json(generic[3]),_raw_json(generic[4])
  if (type(before_items)is not list or len(before_items)!=1 or type(before_items[0])is not dict
      or after_items!=[] or before_items[0]['uid']!=item_uid):raise ValueError('Cartridge singleton receipt inventory')
  old=before_items[0];validate_item(old);rule=source(old);identity=rule['cartridge_id']
  if (type(positions)is not list or len(positions)!=1 or type(positions[0])is not tuple
      or len(positions[0])!=2 or any(type(v)is not int for v in positions[0])):raise ValueError('Cartridge receipt position types')
  if row[4:6]!=(old['template'],identity)or positions!=[(old['group'],old['slot'])]:raise ValueError('Cartridge receipt material/position')
  before,after=_unpacked(row[7]),_unpacked(row[8])
  if after['revision']!=before['revision']+1:raise ValueError('Cartridge receipt account revision')
  expected=dict(before['rows'])
  if identity in expected:
   if row[6]!=0 or after['points']!=before['points']+200:raise ValueError('Cartridge duplicate receipt points')
  else:
   expected[identity]=(0,1)
   if row[6]!=identity or after['points']!=before['points']:raise ValueError('Cartridge new ID receipt')
  if after['rows']!=expected:raise ValueError('Cartridge receipt collection transition')
  return identity,row[6],after['revision']
 except (KeyError,TypeError,json.JSONDecodeError)as exc:raise ValueError('Malformed Cartridge paired history')from exc


def perform(path,owner,account_id,payload,operation,*,authorize=None,now=None,encode=acknowledge):
 (item_uid,)=request(0xd4e,payload);owner,digest=_identity(owner,0xd4e,payload,operation)
 # Only controlled tests inject a clock. Production qualifies after writer lock.
 if now is not None and (type(now)is not int or now<0):raise ValueError('Cartridge use clock')
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  _authority(db,owner,account_id,authorize) # BEFORE previous, even for a retry.
  try:old=_previous(db,operation,digest)
  except (TypeError,KeyError,json.JSONDecodeError)as exc:raise ValueError('Malformed Cartridge previous positions')from exc
  items=load_items(db,owner);current=_read(db,account_id)
  if old is not None:
   identity,response_id,revision=_history(db,operation,digest,owner,account_id,item_uid,old)
   if identity not in current['rows']or current['revision']<revision:raise ValueError('Cartridge current account lost receipt state')
   changed=current_changes(db,operation,owner,0xd4e,old,items)
   event=encode(0xd4f,result=0,identity=response_id,rows=current['rows'],changes=changed,points=current['points'])
   encode_event(event);_authority(db,owner,account_id,authorize);return [event]
  if _schema(db)and db.execute('SELECT 1 FROM account_cartridge_registration_receipts WHERE operation_id=?',(operation,)).fetchone():raise ValueError('Cartridge unpaired account receipt')
  item=next((i for i in items if i['uid']==item_uid),None)
  if item is None:raise ValueError('Cartridge source is not current owned inventory')
  rule=source(item);qualified_now=int(time.time())if now is None else now
  if type(qualified_now)is not int or qualified_now<0:raise ValueError('Cartridge qualification clock')
  require_current(item,now=qualified_now);require_unlocked(item,now=qualified_now)
  identity=rule['cartridge_id'];rows=dict(current['rows']);points=current['points']
  if current['revision']>=2**63-1:raise ValueError('Cartridge account revision overflow')
  if identity in rows:
   if points+200>50000:raise ValueError('Cartridge points overflow rejects whole registration')
   points+=200;response_id=0
  else:rows[identity]=(0,1);response_id=identity
  updated=account_state(rows,points,current['revision']+1)
  _schema(db,create=True)
  db.execute('INSERT INTO account_cartridge_state VALUES (?,?,?) ON CONFLICT(account_id) DO UPDATE SET points=excluded.points,revision=excluded.revision',(account_id,updated['points'],updated['revision']))
  if identity not in current['rows']:db.execute('INSERT INTO account_cartridge_collection VALUES (?,?,?,0)',(account_id,identity,1))
  remove(db,owner,item);after_items=load_items(db,owner)
  actual=_read(db,account_id)
  if actual!=updated:raise ValueError('Cartridge written account state mismatch')
  position=(item['group'],item['slot'])
  event=encode(0xd4f,result=0,identity=response_id,rows=actual['rows'],changes=[(position,None)],points=actual['points'])
  encode_event(event) # Complete ACK before any commit, including lazy DDL.
  _commit(db,operation,digest,owner,0xd4e,[position],[item],[])
  db.execute('INSERT INTO account_cartridge_registration_receipts VALUES (?,?,?,?,?,?,?,?,?,?,?)',
   (operation,digest,account_id,owner,item_uid,item['template'],identity,response_id,
    json.dumps(_packed(current),sort_keys=True),json.dumps(_packed(updated),sort_keys=True),POLICY))
  if {i['uid']:i for i in after_items}!={i['uid']:i for i in items if i['uid']!=item_uid}:raise ValueError('Cartridge source removal changed another instance')
  _authority(db,owner,account_id,authorize)
  return [event]
