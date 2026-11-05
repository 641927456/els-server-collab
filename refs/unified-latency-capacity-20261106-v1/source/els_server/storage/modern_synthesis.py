"""Atomic C68 authority and current-instance receipt replay, no client UI/timer."""
import sqlite3,secrets,json
from contextlib import closing
from collections import Counter
from els_server.protocol.modern_synthesis_messages import request,ack
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.profession_state import require_owner
from els_server.domain.modern_synthesis_rules import quote,draw,require_npc

def perform(path,owner,payload,operation,*,account_id,randbelow=secrets.randbelow,encode=ack):
 rows=request(payload);owner,digest=_identity(owner,0xc68,payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_owner(db,owner,account_id);require_npc(db,owner,account_id)
  old=_previous(db,operation,digest);before=load_items(db,owner)
  balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()
  if balance is None:raise ValueError('Missing synthesis balance')
  ed=balance[0]
  if old is not None:
   rewards=receipt_rewards(db,operation,owner,rows,old)
   changes=current_changes(db,operation,owner,0xc68,old,before)
   events=[Event(0x201,kind=0xc69,payload=encode(ed,changes,rewards))]
   for event in events:encode_event(event)
   return events
  byuid={i['uid']:i for i in before}
  if any(uid not in byuid for uid,_ in rows):raise ValueError('Synthesis requires current owned instances')
  selected=[(byuid[uid],amount)for uid,amount in rows];recipe,count=quote(selected);cost=count*recipe['cost']
  if ed<cost:raise ValueError('Synthesis ED shortage')
  rewards=Counter(draw(recipe,randbelow)for _ in range(count));affected={(i['group'],i['slot'])for i,_ in selected}
  for item,amount in selected:
   if item['count']==amount:remove(db,owner,item)
   else:db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=?',(amount,item['uid'],owner))
  for t,n in sorted(rewards.items()):
   while n:
    amount=min(99,n)
    for item in grant_items(db,[dict(template=t,metadata=2,group=4,quantity=amount)],owner):affected.add((item['group'],item['slot']))
    n-=amount
  db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=?',(cost,owner))
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};positions=sorted(affected)
  events=[Event(0x201,kind=0xc69,payload=encode(ed-cost,[(p,current.get(p))for p in positions],dict(rewards)))]
  for event in events:encode_event(event)
  _commit(db,operation,digest,owner,0xc68,positions,before,after)
  return events


def receipt_rewards(db,operation,owner,rows,positions):
 """Recover exact original results from committed history, never live items.

 C69 map drives native result-template/quality UI even on a replay. Existing
 full before/after receipt arrays retain the exact award (after-before+input).
 No schema, random draw, current inventory inference, or economic write here.
 """
 from els_server.domain.modern_synthesis_rules import catalog
 from els_server.domain.inventory_items import validate_item
 raw=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
 if raw is None or raw[:2]!=(owner,0xc68):raise ValueError('Synthesis receipt owner/kind')
 try:
  before,after=(json.loads(s)for s in raw[2:]);histories=[]
  for items in(before,after):
   if not isinstance(items,list):raise ValueError('Synthesis receipt history array')
   byuid={};points=set()
   for item in items:
    item=validate_item(item);uid=item['uid'];point=(item['group'],item['slot'])
    if uid in byuid or point in points:raise ValueError('Synthesis receipt duplicate instance/position')
    byuid[uid]=item;points.add(point)
   histories.append(byuid)
  old,new=histories;c=catalog();grades=set();baseline={u:i['count']for u,i in old.items()};affected=set()
  for uid,amount in rows:
   i=old.get(uid)
   if(i is None or str(i['template'])not in c['items']or i['group']!=4 or amount>i['count']):raise ValueError('Synthesis receipt original input')
   grades.add(c['items'][str(i['template'])]['grade']);baseline[uid]-=amount;affected.add((i['group'],i['slot']))
  if len(grades)!=1:raise ValueError('Synthesis receipt original quality')
  recipe=c['recipes'][str(grades.pop())];allowed=set(recipe['same_pool']+recipe['upgraded_pool']);rewards=Counter()
  for uid,i in old.items():
   remaining=baseline[uid];j=new.get(uid)
   if remaining==0:
    if j is not None:raise ValueError('Synthesis receipt removed UID recycled')
    continue
   if j is None or any(j.get(k)!=v for k,v in i.items()if k!='count')or any(k not in i for k in j if k!='count'):raise ValueError('Synthesis receipt unrelated instance mutated')
   delta=j['count']-remaining
   if delta<0:raise ValueError('Synthesis receipt unexplained consumption')
   if delta:
    if j['template']not in allowed or(j['metadata'],j['group'])!=(2,4):raise ValueError('Synthesis receipt unadmitted merged output')
    rewards[j['template']]+=delta;affected.add((j['group'],j['slot']))
  for uid,j in new.items():
   if uid in old:continue
   if j['template']not in allowed or(j['metadata'],j['group'])!=(2,4):raise ValueError('Synthesis receipt unadmitted new output')
   rewards[j['template']]+=j['count'];affected.add((j['group'],j['slot']))
  if(positions!=sorted(affected)or any(type(n)is not int or n<=0 for n in rewards.values())or sum(rewards.values())!=sum(n for _,n in rows)//3):raise ValueError('Synthesis receipt result cardinality/positions')
  return dict(rewards)
 except(TypeError,KeyError,IndexError,json.JSONDecodeError)as exc:raise ValueError('Synthesis receipt history format')from exc
