"""Verified magic stones, one atomic authoritative transaction per UI request."""
import secrets,sqlite3,collections
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
def socket(path,owner,payload,operation,randbelow=secrets.randbelow,*,account_id=None):
 uid,materials=request(payload);owner,digest=_identity(owner,0x1c4,payload,operation)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
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
   return [Event(0x201,kind=0x1c5,payload=acknowledgement(balance['ed'],uid,
    [(p,current.get(p)) for p in positions],target.get('option_groups',{}).get('0',[]) if target else []))]
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
  previous=target.get('option_groups',{});updated={**previous,'0':list(previous.get('0',[0]*n))}
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
  replace(db,owner,uid,previous,updated);after=load_items(db,owner)
  current={(i['group'],i['slot']):i for i in after}
  wire=acknowledgement(ed,uid,[(p,current.get(p)) for p in positions],updated['0'])
  _commit(db,operation,digest,owner,0x1c4,positions,before,after)
  return [Event(0x201,kind=0x1c5,payload=wire)]
