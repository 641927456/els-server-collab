"""Artifact changes commit with materials, receipts and preflighted responses."""
import hashlib,json,sqlite3
from contextlib import closing
from els_server.domain import artifact_progression as rules
from els_server.protocol import artifact_messages as wire
from els_server.storage.seal_quests import load_character
from els_server.storage.artifact_receipt_state import replay_changes,store_material_uid

def save(db,character,artifact):
 rules.require_artifact(dict(character,artifact=artifact))
 db.execute('UPDATE character_artifacts SET evolution=?,level=?,experience=?,potentials=? WHERE uid=?',
  (artifact['evolution'],artifact['level'],artifact['experience'],json.dumps(artifact['potentials']),character['uid']))
 db.execute('UPDATE characters SET revision=revision+1 WHERE uid=?',(character['uid'],))

def grow(db,uid,experience):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_artifacts'").fetchone():return False
 if not db.execute('SELECT 1 FROM character_artifacts WHERE uid=?',(uid,)).fetchone():return False
 character=load_character(db,uid);a=rules.grow(character,experience)
 if a==character['artifact']:return False
 save(db,character,a);return True

def complete_quest(db,uid,qid):
 if qid!=54580:return False
 character=load_character(db,uid);a=rules.require_artifact(character)
 if a['evolution']!=4:raise ValueError('Fifth evolution requires stage four')
 save(db,character,dict(a,evolution=5,level=1,experience=0));return True

def consume(db,uid,item,count=1):
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import locked
 require_current(item)
 if item['group']!=4 or locked(item) or type(count) is not int or not 1<=count<=item['count']:raise ValueError('Artifact material unavailable')
 after=dict(item,count=item['count']-count) if item['count']>count else None
 if after:db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=?',(count,uid,item['uid']))
 else:
  from els_server.storage.item_expiration import forget
  forget(db,item['uid'])
  # Locks are absent or expired; remove their historical foreign-key row too.
  if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_locks'").fetchone():db.execute('DELETE FROM item_locks WHERE item_uid=?',(item['uid'],))
  db.execute('DELETE FROM inventory_items WHERE owner=? AND uid=?',(uid,item['uid']))
 return (item['group'],item['slot']),after

def action(path,uid,kind,payload,operation_id,*,account_id=None,randbelow=None,encode=None):
 from els_server.storage.character_schema import character_uid
 from els_server.storage.inventory_state import load_items,owned_template
 from els_server.protocol.career_messages import use_ack
 uid=character_uid(uid)
 if kind not in ('potential','potion') or not isinstance(operation_id,str) or not 1<=len(operation_id)<=200:raise ValueError('Artifact operation identity')
 if not isinstance(payload,bytes) or not 1<=len(payload)<=65536:raise ValueError('Artifact request body')
 request=wire.potential_request(payload) if kind=='potential' else None
 digest=hashlib.sha256(str((uid,kind)).encode()+payload).hexdigest()
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifact_actions'").fetchone()
  old=db.execute('SELECT owner,request_hash,positions FROM artifact_actions WHERE operation_id=?',(operation_id,)).fetchone() if exists else None
  if old and old[:2]!=(uid,digest):raise ValueError('Conflicting artifact retry')
  if kind=='potion':
   # This adapter precedes other 219 consumers. Interpret Artifact-only quantity
   # and reserved fields only after the owned instance (or receipt) identifies it.
   item_uid=int.from_bytes(payload[:8],'big') if len(payload)>=8 else 0
   template=owned_template(db,uid,item_uid)
   if not old and template not in rules.catalog()['level_up_items'] and str(template) not in rules.catalog()['exp_potions']:return None
   request=wire.consumable_request(payload)
  character=load_character(db,uid,account_id);items=load_items(db,uid)
  changes=[];template=0;before=character.get('artifact');reset=False
  refresh=[]
  if old:
   if kind=='potential':reset=request[1]
   changes,refresh=replay_changes(db,operation_id,uid,digest,old[2],items,consumed=kind=='potion' or reset,request_uid=request[0] if kind=='potion' else None)
  elif kind=='potential':
   index,reset,chosen=request
   a=rules.potential(character,index,reset,chosen,**({'randbelow':randbelow} if randbelow else {}))
   if reset:
    from els_server.domain.item_expiration import expired
    from els_server.domain.item_locks import locked
    priority=rules.catalog()['reset_priority']
    valid=[i for i in items if i['group']==4 and i['template'] in priority and not expired(i) and not locked(i)]
    if not valid:raise ValueError('Artifact reset scroll required')
    item=min(valid,key=lambda i:(priority.index(i['template']),i.get('expires_at',2**63),i['slot']))
    changes.append(consume(db,uid,item))
   save(db,character,a)
  else:
   item_uid,count=request;item=next((i for i in items if i['uid']==item_uid),None)
   if item is None or item['template'] not in rules.catalog()['level_up_items'] and str(item['template']) not in rules.catalog()['exp_potions']:return None
   a=rules.use_consumable(character,item['template'],count)
   if a==character['artifact']:raise ValueError('Artifact cannot gain experience at this stage')
   template=item['template'];changes.append(consume(db,uid,item,count));save(db,character,a)
  character=load_character(db,uid,account_id)
  if kind=='potential':events=[wire.potential_ack(character,changes,reset)]
  else:
   ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
   events=[use_ack(changes,template,ed)]
  evolved=not old and before['evolution']!=character['artifact']['evolution']
  events.append(wire.notice(character,evolved))
  if refresh:
   from els_server.storage.inventory_management import _updates
   events.extend(_updates(refresh))
  if encode is not None:events=encode(events)
  if not isinstance(events,list) or any(not isinstance(e.payload,bytes) or not 0<len(e.payload)<=65536 for e in events):raise ValueError('Artifact response bound')
  if not old:
   db.execute('CREATE TABLE IF NOT EXISTS artifact_actions (operation_id TEXT PRIMARY KEY, owner INTEGER NOT NULL, request_hash TEXT NOT NULL, positions TEXT NOT NULL)')
   db.execute('INSERT INTO artifact_actions VALUES (?,?,?,?)',(operation_id,uid,digest,json.dumps([pos for pos,_ in changes])))
   if kind=='potential' and reset:store_material_uid(db,operation_id,uid,digest,changes,items)
  return events

def move(path,payload,uid,*,account_id,session_id,sequence,validate=lambda:None):
 import struct,uuid
 from els_server.domain.inventory_items import validate_item
 from els_server.domain.fashion_state import move_ack
 from els_server.storage.inventory_state import load_items
 from els_server.storage.bag_capacity import allowances
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import locked
 if not isinstance(payload,bytes) or len(payload)!=11:raise ValueError('Artifact equipment request length')
 sg,ss,dg,ds,flag=struct.unpack('>BiBiB',payload);source=(sg,ss);destination=(dg,ds)
 if flag or source==destination or 24 not in (sg,dg):raise ValueError('Artifact equipment request fields')
 if type(account_id) is not int or account_id<=0 or type(session_id) is not str:raise ValueError('Artifact wear identity')
 connection=uuid.UUID(session_id)
 if connection.version!=4 or str(connection)!=session_id or type(sequence) is not int or not 1<=sequence<2**32:raise ValueError('Artifact wear operation')
 operation=session_id+':artifact104:'+str(uid)+':'+str(sequence)
 digest=hashlib.sha256(struct.pack('>Q',uid)+payload).hexdigest();positions_json=json.dumps((source,destination),separators=(',',':'))
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate()
  character=load_character(db,uid,account_id);rules.require_artifact(character);limit=allowances(db,uid)[1]
  if any(not (g==24 and s in range(5) or g==1 and 0<=s<limit) for g,s in (source,destination)):raise ValueError('Artifact equipment position')
  items=load_items(db,uid);by_pos={(i['group'],i['slot']):i for i in items};first=by_pos.get(source);second=by_pos.get(destination)
  exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wear_move_receipts'").fetchone()
  old=db.execute('SELECT owner,account_id,request_hash,positions_json FROM wear_move_receipts WHERE operation_id=?',(operation,)).fetchone() if exists else None
  if old is not None:
   if old!=(uid,account_id,digest,positions_json):raise ValueError('Artifact wear receipt conflict')
   response=move_ack([(source,first),(destination,second)]);validate();return response
  if first is None:raise ValueError('Artifact source is empty')
  for item in (first,second):
   if item:
    require_current(item)
    if locked(item) or not rules.slots(item['template']):raise ValueError('Artifact equipment unavailable')
  moved=validate_item(dict(first,group=dg,slot=ds));swapped=validate_item(dict(second,group=sg,slot=ss)) if second else None
  for item in (moved,swapped):
   if item and item['group']==24:rules.require_wearable(item,character)
  response=move_ack([(source,swapped),(destination,moved)]);validate()
  # Retained UIDs must not trigger CASCADE deletion of opened-slot state.
  # Temporary positions exist only inside this transaction, never on the wire.
  for item in (first,second):
   if item and db.execute('UPDATE inventory_items SET slot=? WHERE owner=? AND uid=?',(-item['uid'],uid,item['uid'])).rowcount!=1:raise ValueError('Artifact source owner mismatch')
  for item in (moved,swapped):
   if item and db.execute('UPDATE inventory_items SET bag_group=?,slot=? WHERE owner=? AND uid=?',(item['group'],item['slot'],uid,item['uid'])).rowcount!=1:raise ValueError('Artifact retained owner mismatch')
  after=load_items(db,uid)
  stable=lambda rows:sorted(({k:v for k,v in i.items() if k not in ('group','slot')} for i in rows),key=lambda i:i['uid'])
  if stable(after)!=stable(items):raise ValueError('Artifact move changed instance data')
  expected={i['uid']:i for i in items};expected.update({i['uid']:i for i in (moved,swapped) if i})
  if expected!={i['uid']:i for i in after}:raise ValueError('Artifact move changed unrelated position')
  db.execute('CREATE TABLE IF NOT EXISTS artifact_moves (id INTEGER PRIMARY KEY, owner INTEGER NOT NULL, request BLOB NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL)')
  db.execute('INSERT INTO artifact_moves(owner,request,before_json,after_json) VALUES (?,?,?,?)',(uid,payload,json.dumps([first,second]),json.dumps([swapped,moved])))
  db.execute("CREATE TABLE IF NOT EXISTS wear_move_receipts (operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,request_hash TEXT NOT NULL CHECK(length(request_hash)=64),positions_json TEXT NOT NULL)")
  db.execute('INSERT INTO wear_move_receipts VALUES (?,?,?,?,?)',(operation,uid,account_id,digest,positions_json));validate()
  return response
