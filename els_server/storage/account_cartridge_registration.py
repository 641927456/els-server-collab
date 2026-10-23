"""Finite account-shared singleton D4E, current-state retries and readonly D4D.

The credential database is never attached or modified. All state and both
receipts share the inventory transaction. Finite armor binding widens only the
known registration schema; client owns effects. Unknown state remains HOLD.
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

from els_server.domain.cartridge_registration_rules import REGISTRATION_SCHEMAS as SCHEMAS
LEGACY=('equipment_cartridge_states','equipment_cartridge_points')


def _authority(db,owner,account_id,authorize):
 if not db.in_transaction:raise ValueError('Cartridge transaction required')
 require_active_character(db,owner);require_owner(db,owner,account_id)
 if authorize is not None and not authorize():raise ValueError('Obsolete Cartridge session')


def _schema(db,*,create=False):
 from els_server.domain.cartridge_registration_rules import schema_kind,REGISTRATION_SCHEMAS
 kind=schema_kind(db)
 if kind!='absent':return True
 if not create:return False
 if db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Cartridge schema foreignkeys required')
 for sql in REGISTRATION_SCHEMAS.values():db.execute(sql)
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
 from els_server.domain.cartridge_registration_rules import legacy_guard,schema_kind
 legacy_guard(db,account_id,schema_kind(db))



def _read(db,account_id):
 from els_server.domain.cartridge_registration_rules import read_account
 return read_account(db,account_id)



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


def _ensure_binding_schema(db):
 from els_server.domain.cartridge_registration_rules import schema_kind,REGISTRATION_SCHEMAS,BINDING_SCHEMAS
 kind=schema_kind(db)
 if kind=='binding':return
 if kind!='registration'or db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Registered known schema required before Cartridge binding')
 # RENAME may rewrite views/external triggers. This finite migration cannot
 # parse or rewrite unknown SQL dependencies; preserve every object by HOLD.
 if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') LIMIT 1").fetchone():raise ValueError('Unknown view/trigger dependency before Cartridge schema widening')
 if db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND tbl_name='account_cartridge_collection' AND sql IS NOT NULL LIMIT 1").fetchone():raise ValueError('Cartridge collection index requires separate migration review')
 if db.execute("SELECT 1 FROM sqlite_master WHERE name='cartridge_collection_old' COLLATE NOCASE").fetchone():raise ValueError('Cartridge migration temporary collision')
 for (table,)in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
  quoted='"'+table.replace('"','""')+'"'
  if any(r[2].lower()=='account_cartridge_collection'for r in db.execute('PRAGMA foreign_key_list('+quoted+')')):raise ValueError('Unknown incoming collection dependency')
 before=db.execute('SELECT account_id,cartridge_id,level,bound_uid FROM account_cartridge_collection ORDER BY account_id,cartridge_id').fetchall()
 db.execute('ALTER TABLE account_cartridge_collection RENAME TO cartridge_collection_old')
 db.execute(BINDING_SCHEMAS['account_cartridge_collection'])
 db.execute('INSERT INTO account_cartridge_collection SELECT account_id,cartridge_id,level,bound_uid FROM cartridge_collection_old')
 db.execute('DROP TABLE cartridge_collection_old')
 db.execute(BINDING_SCHEMAS['account_cartridge_binding_receipts'])
 if schema_kind(db)!='binding'or before!=db.execute('SELECT account_id,cartridge_id,level,bound_uid FROM account_cartridge_collection ORDER BY account_id,cartridge_id').fetchall():raise ValueError('Cartridge widening lost original rows')

def _binding_target(item):
 from els_server.domain.cartridge_registration_rules import binding_catalog
 if(item is None or item['template']not in binding_catalog()or item['metadata']!=1 or item['count']!=1 or item['group']not in(1,9)or'expires_at'in item):raise ValueError('Finite current permanent Cartridge carrier required')
 validate_item(item)
 return item

def _attach_intrinsic(item):
 # Static instance facts also independently required for D50 history. Do not
 # reinterpret old history using current character class/level or clock.
 item=_binding_target(item)
 if(item.get('sealed',False)is not False or item.get('identified',True)is not True
    or item.get('enhancement',0)<0 or item.get('durability',0)<=0):raise ValueError('Cartridge attachment requires unsealed identified unbroken durable carrier')
 return item

def _binding_history(db,operation,digest,owner,account_id,target_uid,kind,selected_id,positions):
 from els_server.domain.cartridge_registration_rules import BINDING_POLICY,scalar,schema_kind
 if schema_kind(db)!='binding':raise ValueError('Cartridge binding receipt schema missing')
 row=db.execute('SELECT request_hash,account_id,actor_uid,target_uid,kind,cartridge_id,before_json,after_json,policy_id FROM account_cartridge_binding_receipts WHERE operation_id=?',(operation,)).fetchone()
 generic=db.execute('SELECT owner,kind,request_hash,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
 if row is None or generic is None or row[:5]!=(digest,account_id,owner,target_uid,kind)or row[8]!=BINDING_POLICY or generic[:3]!=(owner,kind,digest):raise ValueError('Cartridge binding paired receipt identity')
 identity=row[5]
 if type(identity)is not int or not 1<=identity<=19 or kind==0xd50 and selected_id!=identity:raise ValueError('Cartridge binding history selected ID')
 try:
  a,b=_raw_json(generic[3]),_raw_json(generic[4])
  if type(a)is not list or type(b)is not list or len(a)!=1 or len(b)!=1:raise ValueError('Cartridge binding target history shape')
  first,last=_binding_target(a[0]),_binding_target(b[0])
  if first['uid']!=target_uid or last['uid']!=target_uid or {k:v for k,v in first.items()if k!='cartridge'}!={k:v for k,v in last.items()if k!='cartridge'}:raise ValueError('Cartridge binding altered inventory state')
  point=(first['group'],first['slot'])
  if type(positions)is not list or len(positions)!=1 or type(positions[0])is not tuple or len(positions[0])!=2 or any(type(v)is not int for v in positions[0])or positions!=[point]:raise ValueError('Cartridge binding history position')
  before,after=_unpacked(row[6]),_unpacked(row[7]);expected=dict(before['rows'])
  if identity not in expected or after['points']!=before['points']or after['revision']!=before['revision']+1:raise ValueError('Cartridge binding account transition')
  old_uid,level=expected[identity]
  if kind==0xd50:
   _attach_intrinsic(first)
   if old_uid!=0 or scalar(first.get('cartridge',[0,0]))!=[0,0]or scalar(last.get('cartridge',[0,0]))!=[identity,level]:raise ValueError('Cartridge attach history transition')
   expected[identity]=(target_uid,level)
  else:
   if old_uid!=target_uid or scalar(first.get('cartridge',[0,0]))!=[identity,level]or scalar(last.get('cartridge',[0,0]))!=[0,0]:raise ValueError('Cartridge remove history transition')
   expected[identity]=(0,level)
  if after['rows']!=expected:raise ValueError('Cartridge binding changed another account row')
  return identity,after['revision']
 except(KeyError,TypeError,json.JSONDecodeError)as exc:raise ValueError('Malformed Cartridge binding paired history')from exc

def perform_binding(path,owner,account_id,kind,payload,operation,*,authorize=None,encode=acknowledge):
 from els_server.domain.cartridge_registration_rules import BINDING_POLICY,scalar
 if kind not in(0xd50,0xd52):raise ValueError('Finite Cartridge binding action')
 fields=request(kind,payload);target_uid=fields[0];selected_id=fields[1]if kind==0xd50 else None
 owner,digest=_identity(owner,kind,payload,operation)
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');_authority(db,owner,account_id,authorize)
  try:previous=_previous(db,operation,digest)
  except(TypeError,KeyError,json.JSONDecodeError)as exc:raise ValueError('Malformed Cartridge binding previous')from exc
  items=load_items(db,owner);current=_read(db,account_id);item=next((i for i in items if i['uid']==target_uid),None)
  if previous is not None:
   identity,revision=_binding_history(db,operation,digest,owner,account_id,target_uid,kind,selected_id,previous)
   if identity not in current['rows']or current['revision']<revision:raise ValueError('Cartridge binding currentstate lost history')
   # Only the still-current original after-effect is a genuine success retry.
   pair=current['rows'][identity];expected_uid=target_uid if kind==0xd50 else 0
   valid=pair[0]==expected_uid
   try:_binding_target(item)
   except ValueError:valid=False
   expected_pair=[identity,pair[1]]if kind==0xd50 else[0,0]
   if item is None or scalar(item.get('cartridge',[0,0]))!=expected_pair:valid=False
   if not valid:
    event=encode(kind+1,result=2005,identity=0,rows={},changes=());encode_event(event);_authority(db,owner,account_id,authorize);return[event]
   changes=current_changes(db,operation,owner,kind,previous,items)
   event=encode(kind+1,result=0,identity=identity,rows=current['rows'],changes=changes);encode_event(event);_authority(db,owner,account_id,authorize);return[event]
  from els_server.domain.cartridge_registration_rules import schema_kind
  if schema_kind(db)=='binding'and db.execute('SELECT 1 FROM account_cartridge_binding_receipts WHERE operation_id=?',(operation,)).fetchone():raise ValueError('Unpaired Cartridge binding account receipt')
  item=_binding_target(item);rows=dict(current['rows'])
  if current['revision']>=2**63-1:raise ValueError('Cartridge account revision overflow')
  if kind==0xd50:
   _attach_intrinsic(item)
   if selected_id not in rows or rows[selected_id][0]!=0 or scalar(item.get('cartridge',[0,0]))!=[0,0]:raise ValueError('Cartridge ID/target already occupied or unregistered')
   require_current(item);require_unlocked(item)
   from els_server.domain.equipment_instance import require_wearable
   raw=db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(owner,)).fetchone()
   if raw is None:raise ValueError('Cartridge current character missing')
   require_wearable(item,dict(unit_type=raw[0],unit_class=raw[1],level=raw[2]))
   if item.get('sealed',False):raise ValueError('Unseal before Cartridge attachment')
   identity=selected_id;level=rows[identity][1];rows[identity]=(target_uid,level)
  else:
   matches=[i for i,(u,l)in rows.items()if u==target_uid]
   if len(matches)!=1:raise ValueError('Exact current Cartridge carrier binding required')
   identity=matches[0];level=rows[identity][1]
   if scalar(item.get('cartridge',[0,0]))!=[identity,level]:raise ValueError('Current Cartridge projection mismatch')
   rows[identity]=(0,level)
  updated=account_state(rows,current['points'],current['revision']+1)
  _ensure_binding_schema(db)
  if db.execute('UPDATE account_cartridge_collection SET bound_uid=? WHERE account_id=? AND cartridge_id=? AND bound_uid=?',(rows[identity][0],account_id,identity,current['rows'][identity][0])).rowcount!=1:raise ValueError('Cartridge binding conditional update')
  if db.execute('UPDATE account_cartridge_state SET revision=? WHERE account_id=? AND revision=?',(updated['revision'],account_id,current['revision'])).rowcount!=1:raise ValueError('Cartridge account conditional revision')
  after_items=load_items(db,owner);actual=_read(db,account_id)
  if actual!=updated:raise ValueError('Cartridge binding written account mismatch')
  final=next((i for i in after_items if i['uid']==target_uid),None)
  if final is None or {k:v for k,v in final.items()if k!='cartridge'}!={k:v for k,v in item.items()if k!='cartridge'}or {i['uid']:i for i in after_items if i['uid']!=target_uid}!={i['uid']:i for i in items if i['uid']!=target_uid}:raise ValueError('Cartridge binding changed inventory identity/sidecars')
  position=(final['group'],final['slot']);event=encode(kind+1,result=0,identity=identity,rows=actual['rows'],changes=[(position,final)]);encode_event(event)
  _commit(db,operation,digest,owner,kind,[position],[item],[final])
  db.execute('INSERT INTO account_cartridge_binding_receipts VALUES (?,?,?,?,?,?,?,?,?,?)',(operation,digest,account_id,owner,target_uid,kind,identity,json.dumps(_packed(current),sort_keys=True),json.dumps(_packed(updated),sort_keys=True),BINDING_POLICY))
  _authority(db,owner,account_id,authorize);return[event]
