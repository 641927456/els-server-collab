import json,sqlite3,struct,uuid,time
from contextlib import closing
from els_server.domain.boosting_2026_accessories import BOXES,boxes,items
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_management import _updates
from els_server.storage.npc_trade import balances
from els_server.storage.item_instances import remove
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event,Event
from els_server.domain.fashion_state import move_ack
def open_box(path,owner,template,payload,operation,*,now=None):
 rule=boxes().get(template);req=use_request(payload)
 if rule is None or req.option not in (0,1) or req.choices or any(v not in (0,1) for v in (req.flag1,req.flag2,req.flag3)):raise ValueError('Selected accessory box is all-output, no choices')
 owner,digest=_identity(owner,0x196,struct.pack('>i',template)+payload,operation)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
  if old is not None:return _updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
  source=next((i for i in before if i['uid']==req.uid),None)
  if source is None or source['template']!=template or source['group']!=4:raise ValueError('Owned selected accessory source box required')
  value=int(time.time()) if now is None else now
  if type(value) is not int or not 0<=value<2**40-90*86400:raise ValueError('Selected accessory opening epoch')
  require_current(source,now=value);require_unlocked(source,now=value)
  if balance['revision']>=2**63-1:raise ValueError('Selected accessory revision overflow')
  position=(source['group'],source['slot'])
  if source['count']==1:remove(db,owner,source)
  else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(source['uid'],owner))
  from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
  plans=[]
  for r in rule['outputs']:
   t=r['template'];plan=dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=r['quantity']);days=items().get(t,{}).get('period_days',0)
   if days:plan['expires_at']=value+days*86400
   plans.append(plan)
  grants=grant_items(db,plans,owner,selected_accessory_box=template);after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};positions=sorted({position,*[(i['group'],i['slot']) for i in grants]});events=result(balance['ed'],[(p,current.get(p)) for p in positions],[(r['template'],r['quantity']) for r in rule['outputs']])
  for event in events:encode_event(event)
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,));_commit(db,operation,digest,owner,0x196,positions,before,after);return events