"""Verified magic stones, one atomic authoritative transaction per UI request."""
import secrets,sqlite3,collections,json
from contextlib import closing
from els_server.domain.sage_sockets import STONE,capacity,draw,fee,distribution
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.socket_messages import request,acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances,charge
from els_server.storage.equipment_options import replace

def _results(values,materials):
 # The native preview pairs one rolled value with each requested material row;
 # a capacity-length vector padded with zero reads as unknown option 0.
 return [values[slot] if slot<len(values) else 0 for slot in materials]

def socket(path,owner,payload,operation,randbelow=secrets.randbelow,*,account_id=None,session_id=None,prepare=None):
 uid,materials=request(payload);owner,digest=_identity(owner,0x1c4,payload,operation)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  if prepare is not None:prepare()
  from els_server.storage.item_actor import require_active_character
  require_active_character(db,owner)
  if not isinstance(session_id,str)or not 1<=len(session_id)<=160:raise ValueError('Socket preview session identity')
  if account_id is not None:
   from els_server.storage.profession_state import require_owner
   require_owner(db,owner,account_id)
  old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
  current={(i['group'],i['slot']):i for i in before};by_uid={i['uid']:i for i in before}
  target=by_uid.get(uid)
  if old is not None:
   # Keep historical slots current, including replacement occupants, and also
   # refresh the original request's surviving UIDs at their present positions.
   # The native consumer applies this vector by slot; its options vector alone
   # does not update inventory after an item has moved.
   affected={uid,*materials.values()}
   positions=list(dict.fromkeys([*old,*[(i['group'],i['slot']) for i in before if i['uid'] in affected]]))
   candidate=(_pending(db,owner,uid,session_id,target) or {}).get('candidate',target.get('option_groups',{}).get('0',[])) if target else []
   return [Event(0x201,kind=0x1c5,payload=acknowledgement(balance['ed'],uid,
    [(p,current.get(p)) for p in positions],_results(candidate,materials)))]
  if target is None or target['count']!=1:raise ValueError('Socket target not owned')
  if target.get('enhancement',0)<0:raise ValueError('Broken equipment requires restoration')
  require_current(target);require_unlocked(target);n=capacity(target['template'])
  if any(k>=n for k in materials):raise ValueError('Socket exceeds original capacity')
  counts=collections.Counter(materials.values())
  from els_server.domain.atma_sockets import catalog as atma_catalog
  from els_server.domain.additional_magic_stones import catalog as additional_catalog
  from els_server.domain.ordinary_magic_stones import catalog as ordinary_catalog
  profiles={}
  for material_uid,count in counts.items():
   material=by_uid.get(material_uid)
   if material is None or (material['template']!=STONE and str(material['template']) not in atma_catalog()['items'] and str(material['template']) not in additional_catalog()['items'] and str(material['template']) not in ordinary_catalog()['items']) or material['count']<count:raise ValueError('Missing owned supported magic stones')
   require_current(material);require_unlocked(material)
   profiles[material_uid]=distribution(target,material['template']) # All admissions precede RNG.
  ed=charge(db,owner,balance,sum(fee(target,by_uid[m]['template']) for m in materials.values()))
  previous=target.get('option_groups',{});pending=_pending(db,owner,uid,session_id,target)
  updated={**previous,'0':list(pending['candidate'] if pending else previous.get('0',[0]*n))}
  rolled=set(pending['slots'])if pending else set();rolled.update(materials)
  for slot in sorted(materials):
   material_uid=materials[slot]
   # A native fixed-value stone has one 100% result; it never draws RNG.
   roll=0 if len(profiles[material_uid])==1 else randbelow(10000)
   updated['0'][slot]=draw(target,roll,by_uid[material_uid]['template'])
  positions=[(target['group'],target['slot'])]
  for material_uid,count in counts.items():
   material=by_uid[material_uid];positions.append((material['group'],material['slot']))
   if material['count']==count:remove(db,owner,material)
   else:db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=?',(count,owner,material_uid))
  _stage(db,owner,uid,session_id,operation,target,updated['0'],rolled)
  after=load_items(db,owner)
  current={(i['group'],i['slot']):i for i in after}
  wire=acknowledgement(ed,uid,[(p,current.get(p)) for p in positions],_results(updated['0'],materials))
  event=Event(0x201,kind=0x1c5,payload=wire)
  from els_server.protocol.protocol_codec import encode_event
  encode_event(event)
  if prepare is not None:prepare()
  _commit(db,operation,digest,owner,0x1c4,positions,before,after)
  return [event]

PENDING='equipment_socket_pending'

def _pending(db,owner,uid,session_id,target):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(PENDING,)).fetchone():return None
 row=db.execute('SELECT session_id,operation_id,target_json,candidate_json,slots_json FROM '+PENDING+' WHERE owner=? AND item_uid=?',(owner,uid)).fetchone()
 if row is None or row[0]!=session_id or row[2]!=json.dumps(target,sort_keys=True):return None
 return dict(operation=row[1],candidate=json.loads(row[3]),slots=json.loads(row[4]))

def _stage(db,owner,uid,session_id,operation,target,candidate,slots):
 if not isinstance(session_id,str)or not 1<=len(session_id)<=160:raise ValueError('Socket preview session identity')
 db.execute("""CREATE TABLE IF NOT EXISTS equipment_socket_pending (
  owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
  item_uid INTEGER NOT NULL REFERENCES inventory_items(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,session_id TEXT NOT NULL,
  operation_id TEXT NOT NULL,target_json TEXT NOT NULL,candidate_json TEXT NOT NULL,
  slots_json TEXT NOT NULL,PRIMARY KEY(owner,item_uid))""")
 db.execute('INSERT INTO '+PENDING+' VALUES (?,?,?,?,?,?,?) ON CONFLICT(owner,item_uid) DO UPDATE SET session_id=excluded.session_id,operation_id=excluded.operation_id,target_json=excluded.target_json,candidate_json=excluded.candidate_json,slots_json=excluded.slots_json',
  (owner,uid,session_id,operation,json.dumps(target,sort_keys=True),json.dumps(candidate),json.dumps(sorted(slots))))

def apply(path,owner,payload,operation,*,account_id=None,session_id=None,prepare=None):
 from els_server.protocol.socket_messages import apply_request,apply_acknowledgement
 from els_server.storage.equipment_receipt_state import current_changes
 from els_server.storage.item_actor import require_active_character
 uid,selected=apply_request(payload);owner,digest=_identity(owner,0x8b1,payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  if prepare is not None:prepare()
  if not isinstance(session_id,str)or not 1<=len(session_id)<=160:raise ValueError('Socket Apply session identity')
  require_active_character(db,owner)
  if account_id is not None:
   from els_server.storage.profession_state import require_owner
   require_owner(db,owner,account_id)
  old=_previous(db,operation,digest);before=load_items(db,owner)
  if old is not None:
   wire=apply_acknowledgement(uid,changes=current_changes(db,operation,owner,0x8b1,old,before))
   return [Event(0x201,kind=0x8b2,payload=wire)]
  target=next((i for i in before if i['uid']==uid),None)
  if target is None or target['count']!=1 or target.get('enhancement',0)<0:raise ValueError('Socket Apply current owned target')
  require_current(target);require_unlocked(target);n=capacity(target['template'])
  pending=_pending(db,owner,uid,session_id,target)
  if pending is None:raise ValueError('No current owned socket preview generation')
  original=target.get('option_groups',{});prior=list(original.get('0',[0]*n));candidate=pending['candidate'];rolled=set(pending['slots'])
  if len(candidate)!=n or len(prior)!=n or any(k>=n for k in selected):raise ValueError('Socket Apply slot capacity')
  values=[selected.get(k,0)for k in range(n)]
  for k,value in enumerate(values):
   allowed={prior[k],candidate[k]}if k in rolled else{prior[k]}
   if value not in allowed:raise ValueError('Socket Apply value not generated for this slot')
  updated=original if values==prior else{**original,'0':values}
  if updated!=original:replace(db,owner,uid,original,updated)
  db.execute('DELETE FROM '+PENDING+' WHERE owner=? AND item_uid=? AND session_id=?',(owner,uid,session_id))
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};positions=[(target['group'],target['slot'])]
  wire=apply_acknowledgement(uid,changes=[(p,current[p])for p in positions]);event=Event(0x201,kind=0x8b2,payload=wire)
  from els_server.protocol.protocol_codec import encode_event
  encode_event(event)
  if prepare is not None:prepare()
  _commit(db,operation,digest,owner,0x8b1,positions,before,after)
  return [event]
