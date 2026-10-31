"""Consume one owned current convenience box and commit its exact timed contents."""
import hashlib,sqlite3,struct,time,uuid
from contextlib import closing
from els_server.domain.promotion_reward_boxes import BOXES,POLICY,DATA_SHA,plan_for,catalog,outputs_for
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_management import _updates
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances
from els_server.domain.raid_reward_items import _issue_source,plain_plan

def authorize(db,owner,account_id,prepare):
 if not db.in_transaction or not callable(prepare):raise ValueError('Career box transaction authority')
 prepare(db)
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.profession_state import require_owner
 require_active_character(db,owner);require_owner(db,owner,account_id)
 return True

def open_box(path,owner,template,payload,operation,*,account_id,prepare,now=None):
 request=use_request(payload)
 if template not in BOXES or request.option or request.choices or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3)):
  raise ValueError('Career box box has no client-selected outputs')
 owner,digest=_identity(owner,0x196,struct.pack('>i',template)+payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');authorize(db,owner,account_id,prepare)
  old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
  if old is not None:
   events=_updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
   for event in events:encode_event(event)
   authorize(db,owner,account_id,prepare);return events
  item=next((i for i in before if i['uid']==request.uid),None)
  if item is None or item['template']!=template or item['group']!=4:raise ValueError('Exact owned job convenience box required')
  epoch=int(time.time())if now is None else now
  character=db.execute('SELECT unit_class,level FROM characters WHERE uid=?',(owner,)).fetchone()
  if character is None or character[1]<({109999:15,110850:35,135867:99,135869:99}[template]):raise ValueError('Career box native level')
  unit_class=character[0];plan=plan_for(template,epoch,unit_class);require_current(item,now=epoch);require_unlocked(item,now=epoch)
  if item.get('sealed',False):raise ValueError('Sealed career box')
  if balance['revision']>=2**63-1:raise ValueError('Career box revision overflow')
  source=dict(unit_class=unit_class,template=template,uid=item['uid'],owner=owner,epoch=epoch,policy=POLICY,definition_sha256=DATA_SHA,
      owned_instance_sha256=hashlib.sha256(plain_plan(item).encode()).hexdigest())
  cap=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'career-box:'+operation)),'box',source,plan,
      lambda writer:authorize(writer,owner,account_id,prepare))
  position=(item['group'],item['slot'])
  if item['count']==1:remove(db,owner,item)
  else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
  grants=grant_items(db,plan,owner,raid_reward_source=cap)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  positions=sorted({position,*[(i['group'],i['slot'])for i in grants]})
  outputs=outputs_for(template,unit_class)
  events=result(balance['ed'],[(p,current.get(p))for p in positions],[(r['template'],r['quantity'])for r in outputs])
  for event in events:encode_event(event)
  authorize(db,owner,account_id,prepare)
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
  _commit(db,operation,digest,owner,0x196,positions,before,after)
  return events

def preview(path,owner,account_id,template,prepare):
 with closing(sqlite3.connect(path))as db:
  db.execute('BEGIN');authorize(db,owner,account_id,prepare)
  character=db.execute('SELECT unit_class,level FROM characters WHERE uid=?',(owner,)).fetchone()
  if character is None or character[1]<({109999:15,110850:35,135867:99,135869:99}[template]):raise ValueError('Career box native level')
  outputs=outputs_for(template,character[0]);items=load_items(db,owner)
  candidates=[i for i in items if i['template']==template and i['group']==4]
  if not candidates:raise ValueError('Held career box required')
  import time
  now=int(time.time());valid=[]
  for item in candidates:
   try:require_current(item,now=now);require_unlocked(item,now=now)
   except ValueError:continue
   if not item.get('sealed',False):valid.append(item)
  if not valid:raise ValueError('Current unlocked career box required')
  authorize(db,owner,account_id,prepare);return outputs
