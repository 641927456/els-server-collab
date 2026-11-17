"""Consume one owned career box and commit its configured outfit."""
import hashlib,sqlite3,struct,time,uuid
from contextlib import closing
from els_server.domain.anniversary_promotion import BOXES as ANNIVERSARY_BOXES
from els_server.domain.anniversary_extras import TRANSPARENT_BOX
from els_server.domain.promotion_reward_boxes import BOXES,MINIMUM_LEVELS,POLICY,definition_sha,plan_for,outputs_for
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
from els_server.storage.anniversary_promotion import owns_box

def authorize(db,owner,account_id,prepare):
 if not db.in_transaction or not callable(prepare):raise ValueError('Career box transaction authority')
 prepare(db)
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.profession_state import require_owner
 require_active_character(db,owner);require_owner(db,owner,account_id)
 return True

def eligible_class(db,owner,template,minor):
 character=db.execute('SELECT unit_class,level,transcendence,unit_type FROM characters WHERE uid=?',(owner,)).fetchone()
 if character is None or character[1]<MINIMUM_LEVELS[template]:raise ValueError('Career box native level')
 if template in ANNIVERSARY_BOXES and not character[2]:raise ValueError('Anniversary outfit requires a third-job character')
 active=0
 if template==TRANSPARENT_BOX:
  from els_server.storage.luciel_state import active_state
  active=active_state(db,owner)['active_unit'] if character[3]==10 else 0
  if active!=minor:raise ValueError('Transparent outfit opening side mismatch')
 return character[0],active

def open_box(path,owner,template,payload,operation,*,account_id,prepare,now=None):
 request=use_request(payload)
 if template not in BOXES or request.option not in(0,1) or request.choices or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3)):
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
  unit_class,active=eligible_class(db,owner,template,request.flag2)
  if template in ANNIVERSARY_BOXES and not owns_box(db,account_id,item):raise ValueError('Anniversary mail attachment required')
  plan=plan_for(template,epoch,unit_class,active);require_current(item,now=epoch);require_unlocked(item,now=epoch)
  if item.get('sealed',False):raise ValueError('Sealed career box')
  if balance['revision']>=2**63-1:raise ValueError('Career box revision overflow')
  source=dict(unit_class=unit_class,template=template,uid=item['uid'],owner=owner,epoch=epoch,policy=POLICY,definition_sha256=definition_sha(template),
      owned_instance_sha256=hashlib.sha256(plain_plan(item).encode()).hexdigest())
  if template==TRANSPARENT_BOX:source['active']=active
  cap=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'career-box:'+operation)),'box',source,plan,
      lambda writer:authorize(writer,owner,account_id,prepare))
  position=(item['group'],item['slot'])
  if item['count']==1:remove(db,owner,item)
  else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
  grants=grant_items(db,plan,owner,raid_reward_source=cap)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  positions=sorted({position,*[(i['group'],i['slot'])for i in grants]})
  outputs=outputs_for(template,unit_class,active)
  events=result(balance['ed'],[(p,current.get(p))for p in positions],[(r['template'],r['quantity'])for r in outputs])
  for event in events:encode_event(event)
  authorize(db,owner,account_id,prepare)
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
  _commit(db,operation,digest,owner,0x196,positions,before,after)
  return events

def preview(path,owner,account_id,template,prepare,*,minor=0):
 with closing(sqlite3.connect(path))as db:
  db.execute('BEGIN');authorize(db,owner,account_id,prepare)
  unit_class,active=eligible_class(db,owner,template,minor)
  outputs=outputs_for(template,unit_class,active);items=load_items(db,owner)
  candidates=[i for i in items if i['template']==template and i['group']==4]
  if not candidates:raise ValueError('Held career box required')
  import time
  now=int(time.time());valid=[]
  for item in candidates:
   try:require_current(item,now=now);require_unlocked(item,now=now)
   except ValueError:continue
   if not item.get('sealed',False) and (template not in ANNIVERSARY_BOXES or owns_box(db,account_id,item)):valid.append(item)
  if not valid:raise ValueError('Current unlocked career box required')
  authorize(db,owner,account_id,prepare);return outputs
