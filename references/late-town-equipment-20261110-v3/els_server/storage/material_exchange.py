"""Shared NPC material exchanges, with atomic draws, debit, rewards and receipt."""
import sqlite3,struct,time
from contextlib import closing
from pathlib import Path
from els_server.domain.manufacture_requirements import inventory_candidates
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage.reward_state import validate_balances
from els_server.storage.item_actor import require_active_character
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,LOCAL_MAX_STACK
from els_server.protocol.protocol_codec import Event,encode_event

def exchange(path,owner,town,payload,operation,r,*,account_id,source_quantity,acknowledgement,guard,destination=None,output_quantity=None,draw=None,now=None,source_factory=None,reserve=None):
 if (now is not None and (type(now) is not int or now<0)) or type(account_id) is not int or not 1<=account_id<2**63:raise ValueError('Material exchange clock/account')
 owner,digest=_identity(owner,0x223,struct.pack('>i',town)+payload,operation)
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db);require_active_character(db,owner)
  if not db.execute('SELECT 1 FROM character_owners WHERE uid=?AND account_id=?',(owner,account_id)).fetchone():raise ValueError('Material exchange owner')
  location=db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(owner,)).fetchone()
  if location is None or location[0]!=town:raise ValueError('Material exchange saved town')
  def validate():
   guard(db)
   if db.execute('SELECT town,board,progress,x,y,z,revision FROM location WHERE uid=?',(owner,)).fetchone()!=location:raise ValueError('Material exchange location changed')
  before=load_items(db,owner);balance=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone());old=_previous(db,operation,digest)
  if old is not None:
   changes=current_changes(db,operation,owner,0x223,old,before)
   events=[Event(0x201,kind=0x224,payload=acknowledgement(balance['ed'],changes))]
   for event in events:encode_event(event)
   validate();return events
  if now is None:now=int(time.time())
  if reserve is not None:reserve(db,now)
  demand=source_quantity*r.quantity;candidates=inventory_candidates(before,now=now).get(r.source,())
  if sum(n for uid,n in candidates)<demand:raise ValueError('Insufficient current unlocked material')
  by_uid={i['uid']:i for i in before};positions=[]
  for uid,count in sorted(candidates,key=lambda p:(by_uid[p[0]]['group'],by_uid[p[0]]['slot'])):
   if not demand:break
   item=by_uid[uid];take=min(count,demand);demand-=take;positions.append((item['group'],item['slot']))
   if take==count:remove(db,owner,item)
   elif db.execute('UPDATE inventory_items SET count=count-?WHERE uid=?AND owner=?AND count=?',(take,uid,owner,count)).rowcount!=1:raise ValueError('Material exchange stack changed')
  rewards,ed_reward=({destination:output_quantity*r.quantity},0)if draw is None else draw(r.quantity)
  plan=[]
  for template,total in rewards.items():
   cap=min(TEMPLATE_MAX_STACKS[template],LOCAL_MAX_STACK)
   plan.extend(dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=min(cap,total-offset))for offset in range(0,total,cap))
  source=None if source_factory is None else source_factory(db,owner,operation,plan,validate)
  added=[]
  for start in range(0,len(plan),36):added.extend(grant_items(db,plan[start:start+36],owner,raid_reward_source=source))
  if ed_reward:
   balance=validate_balances((balance['ed']+ed_reward,balance['experience'],balance['revision']+1))
   db.execute('UPDATE reward_balances SET ed=?,revision=?WHERE uid=?',(balance['ed'],balance['revision'],owner))
  positions=list(dict.fromkeys(positions+[(i['group'],i['slot'])for i in added]))
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};changes=[(p,current.get(p))for p in positions]
  body=acknowledgement(balance['ed'],changes,list(rewards.items()))if draw is None else acknowledgement(balance['ed'],changes,list(rewards.items()),ed_reward=ed_reward)
  events=[Event(0x201,kind=0x224,payload=body)]
  for event in events:encode_event(event)
  validate();_commit(db,operation,digest,owner,0x223,positions,before,after)
  from els_server.storage.growth_guide import record as guide_record
  guide_record(db,owner,43,quantity=r.quantity,templates=(r.source,))
  return events
