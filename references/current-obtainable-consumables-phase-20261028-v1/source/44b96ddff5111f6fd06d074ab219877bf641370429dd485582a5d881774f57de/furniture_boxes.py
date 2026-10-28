"""Original196 owned current small furniture cube, atomic normal initial equipment."""
from contextlib import closing
import sqlite3,struct,time
from els_server.domain.furniture_rules import TEMPLATE,definitions,plan,POLICY
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_management import _updates
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances
WRITES_ENABLED=True

def authority(db,owner,account,guard):
 if not db.in_transaction or not callable(guard):raise ValueError('Furniture current transaction')
 guard(db)
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.profession_state import require_owner
 require_active_character(db,owner);require_owner(db,owner,account)
 character=db.execute('SELECT unit_type,level FROM characters WHERE uid=?',(owner,)).fetchone()
 if character is None or not 1<=character[1]<=99:raise ValueError('Furniture current character')
 definitions();return character
def usable(item,stamp):
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 if(item['template'],item['metadata'],item['group'],item['count'])!=(TEMPLATE,0,4,1)or item.get('sealed',False)or item.get('seal_count',0):raise ValueError('Furniture owned singleton source')
 require_current(item,now=stamp);require_unlocked(item,now=stamp)
def preview(path,owner,account,guard):
 with closing(sqlite3.connect(path,timeout=10))as db:
  db.execute('BEGIN');character=authority(db,owner,account,guard);valid=False
  for item in load_items(db,owner):
   if item['template']!=TEMPLATE:continue
   try:usable(item,int(time.time()));valid=True
   except ValueError:continue
  if not valid:raise ValueError('Held current small furniture box required')
  if authority(db,owner,account,guard)!=character:raise ValueError('Furniture preview actor changed')
  return definitions()
def perform(path,owner,account,payload,operation,guard,*,now=None):
 request=use_request(payload)
 if request.option or request.choices or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3)):raise ValueError('Furniture original unselected box parameters')
 owner,digest=_identity(owner,0x196,struct.pack('>i',TEMPLATE)+payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');character=authority(db,owner,account,guard)
  before=load_items(db,owner);old=_previous(db,operation,digest);balance=balances(db,owner)
  if old is not None:
   answer=_updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
   for event in answer:encode_event(event)
   authority(db,owner,account,guard);return answer
  if not WRITES_ENABLED:raise ValueError('Furniture writer held')
  item=next((i for i in before if i['uid']==request.uid),None)
  if item is None:raise ValueError('Furniture owned source UID')
  stamp=int(time.time())if now is None else now
  if type(stamp)is not int or stamp<=0:raise ValueError('Furniture use clock')
  usable(item,stamp)
  if balance['revision']>=2**63-1:raise ValueError('Furniture revision bound')
  from els_server.domain.raid_reward_items import _issue_source
  import uuid
  cap=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'furniture-box:'+operation)),'box',dict(template=TEMPLATE,uid=item['uid'],owner=owner,policy=POLICY),plan(),lambda writer:authority(writer,owner,account,guard)is not None)
  remove(db,owner,item);grants=grant_items(db,plan(),owner,raid_reward_source=cap)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};position=(item['group'],item['slot']);positions=sorted({position,*[(i['group'],i['slot'])for i in grants]})
  answer=result(balance['ed'],[(p,current.get(p))for p in positions],[(r['template'],r['quantity'])for r in definitions()])
  for event in answer:encode_event(event)
  if authority(db,owner,account,guard)!=character or not WRITES_ENABLED or balances(db,owner)!=balance or load_items(db,owner)!=after:raise ValueError('Furniture late authority changed')
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,));_commit(db,operation,digest,owner,0x196,positions,before,after)
  return answer
