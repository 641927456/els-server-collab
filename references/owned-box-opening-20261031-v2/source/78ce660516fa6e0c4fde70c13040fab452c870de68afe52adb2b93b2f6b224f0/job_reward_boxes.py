"""Consume one owned current convenience box and commit its exact timed contents."""
import hashlib,sqlite3,struct,time,uuid
from contextlib import closing
from els_server.domain.job_reward_boxes import BOXES,POLICY,DATA_SHA,plan_for,catalog
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
 if not db.in_transaction or not callable(prepare):raise ValueError('Job convenience transaction authority')
 prepare(db)
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.profession_state import require_owner
 require_active_character(db,owner);require_owner(db,owner,account_id)
 return True

def open_box(path,owner,template,payload,operation,*,account_id,prepare,now=None):
 request=use_request(payload)
 if template not in BOXES or request.option not in(0,1) or request.choices or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3)):
  raise ValueError('Job convenience box has no client-selected outputs')
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
  plan=plan_for(template,epoch);require_current(item,now=epoch);require_unlocked(item,now=epoch)
  if balance['revision']>=2**63-1:raise ValueError('Job convenience revision overflow')
  source=dict(template=template,uid=item['uid'],owner=owner,epoch=epoch,policy=POLICY,definition_sha256=DATA_SHA,
      owned_instance_sha256=hashlib.sha256(plain_plan(item).encode()).hexdigest())
  cap=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'job-convenience:'+operation)),'box',source,plan,
      lambda writer:authorize(writer,owner,account_id,prepare))
  position=(item['group'],item['slot'])
  if item['count']==1:remove(db,owner,item)
  else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
  grants=grant_items(db,plan,owner,raid_reward_source=cap)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  positions=sorted({position,*[(i['group'],i['slot'])for i in grants]})
  outputs=catalog()['boxes'][str(template)]['outputs']
  events=result(balance['ed'],[(p,current.get(p))for p in positions],[(r['template'],r['quantity'])for r in outputs])
  for event in events:encode_event(event)
  authorize(db,owner,account_id,prepare)
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
  _commit(db,operation,digest,owner,0x196,positions,before,after)
  return events
