"""Original owned Raid boxes and native pity actions, one real SQL transaction."""
import hashlib,json,secrets,sqlite3,struct,uuid
from contextlib import closing
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_management import _updates
from els_server.storage.npc_trade import balances
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.domain.raid_reward_items import boxes,entry_outputs,_issue_source
from els_server.domain import formal_raid_economy as rules
from els_server.storage import raid_economy_state as state

def authorize(db,owner,account_id,guard):
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.profession_state import require_owner
 if not db.in_transaction or not callable(guard)or guard()is not True:raise ValueError('Raid native action authority')
 require_active_character(db,owner);require_owner(db,owner,account_id)
 return True

def prepare_events(events):
 from els_server.protocol.protocol_codec import encode_event
 for e in events:encode_event(e)
 return events

def historical_box(path,owner,payload,operation):
 from els_server.protocol.ice_messages import use_request
 request=use_request(payload)
 with closing(sqlite3.connect(path,timeout=10))as db:
  if not state.exists(db,'inventory_action_receipts'):return None
  row=db.execute('SELECT request_hash,owner,kind,before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
  if row is None or row[1:3]!=(owner,0x196):return None
  candidates=[i['template']for i in json.loads(row[3])if i['uid']==request.uid and str(i['template'])in boxes()]
  if len(candidates)!=1:return None
  expected=candidates[0]
  if _identity(owner,0x196,struct.pack('>i',expected)+payload,operation)[1]!=row[0]:raise ValueError('Conflicting Raid owned box replay')
  return expected

def open_box(path,owner,template,payload,operation,account_id,guard):
 from els_server.protocol.ice_messages import use_request
 from els_server.protocol.cube_messages import result
 from els_server.storage.item_instances import remove
 from els_server.storage.seal_quests import load_character
 request=use_request(payload)
 if str(template)not in boxes()or request.option or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3)):raise ValueError('Raid box exact original request')
 owner,digest=_identity(owner,0x196,struct.pack('>i',template)+payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');authorize(db,owner,account_id,guard)
  old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
  if old is not None:
   events=_updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed']);prepare_events(events);authorize(db,owner,account_id,guard);return events
  item=next((i for i in before if i['uid']==request.uid),None)
  if item is None or item['template']!=template or item['group']!=4:raise ValueError('Raid exact owned box instance')
  require_current(item);require_unlocked(item)
  row,weapon_outputs=entry_outputs(template,load_character(db,owner,account_id))
  if row['selection_count']:
   if len(request.choices)!=1 or request.choices[0]not in{e['template']for e in row['entries']}:raise ValueError('Raid native box selection outside exact options')
   choice=request.choices[0]
   outputs=weapon_outputs if row['mode']=='class_select'and choice==weapon_outputs[0]['template']else [next(e for e in row['entries']if e['template']==choice)]
  else:
   if request.choices:raise ValueError('Raid fixed/class box does not accept arbitrary choices')
   outputs=[row['entries'][secrets.randbelow(len(row['entries']))]]if row['mode']=='random'else weapon_outputs
  from els_server.domain.reward_rules import item_plan
  plan=[]
  for selected in outputs:
   p=item_plan(selected['template'],selected['quantity'])
   if 'enhancement'in selected:p['enhancement']=selected['enhancement']
   plan.append(p)
  op=str(uuid.uuid5(uuid.NAMESPACE_URL,'raid-owned-box:'+operation))
  source=dict(template=template,uid=item['uid'],owner=owner,operation=operation,owned_instance_sha256=hashlib.sha256(state.canonical(item).encode()).hexdigest())
  cap=_issue_source(db,owner,op,'box',source,plan,lambda writer:authorize(writer,owner,account_id,guard))
  position=(item['group'],item['slot'])
  if item['count']==1:remove(db,owner,item)
  else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
  grants=grant_items(db,plan,owner,raid_reward_source=cap)
  if template==136180:
   # Only this already-authorized owned-box writer can initialize fresh136186.
   # Never retrofit a historical UID or touch other class outputs.
   old_uids={i['uid']for i in before}
   from els_server.storage.equipment_identification import replace as identify_state
   for issued in grants:
    if issued['template']!=136186:continue
    if issued['uid']in old_uids or issued['group']!=1 or issued['count']!=1 or 'identified'in issued or issued.get('option_groups',{}).get('1'):
     raise ValueError('Fresh death-dragon owned-box identification source')
    identify_state(db,owner,issued['uid'],False,False)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
  positions=sorted({position,*[(i['group'],i['slot'])for i in grants]})
  events=result(balance['ed'],[(p,current.get(p))for p in positions],[(r['template'],r['quantity'])for r in outputs]);prepare_events(events)
  if balance['revision']>=2**63-1:raise ValueError('Raid box balance revision overflow')
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
  _commit(db,operation,digest,owner,0x196,positions,before,after);authorize(db,owner,account_id,guard);return events

def claim(path,owner,payload,operation,account_id,guard):
 from els_server.protocol.raid_economy_protocol import claim_ack,point_snapshot
 if len(payload)!=8:raise ValueError('Native Raid point claim length')
 group,subtype=struct.unpack('>ii',payload);targets={1:136175,2:136179,3:30876}
 if group!=1 or subtype not in targets:raise ValueError('Native Raid point claim subtype')
 owner,digest=_identity(owner,0xc06,payload,operation);key='accessory:'+str(subtype)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');authorize(db,owner,account_id,guard)
  old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
  if old is not None:
   events=_updates(current_changes(db,operation,owner,0xc06,old,before))+[claim_ack()];prepare_events(events);authorize(db,owner,account_id,guard);return events
  points,generation=state.progress(db,owner,key)
  if points!=100:raise ValueError('Raid accessory pity is not full')
  state.ensure(db);plan=rules.plan([(targets[subtype],1)]);op=str(uuid.uuid5(uuid.NAMESPACE_URL,'raid-accessory-pity:'+operation))
  cap=_issue_source(db,owner,op,'pity',dict(owner=owner,subtype=subtype,generation=generation,points=points,operation=operation),plan,lambda writer:authorize(writer,owner,account_id,guard))
  grants=grant_items(db,plan,owner,raid_reward_source=cap);state.set_progress(db,owner,key,0,generation+1)
  after=load_items(db,owner);positions=sorted({(i['group'],i['slot'])for i in grants})
  events=[claim_ack(grants),point_snapshot([(n,state.progress(db,owner,'accessory:'+str(n))[0],t)for n,t in targets.items()],db=db,owner=owner)];prepare_events(events)
  if balance['revision']>=2**63-1:raise ValueError('Raid pity balance revision overflow')
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,));_commit(db,operation,digest,owner,0xc06,positions,before,after)
  authorize(db,owner,account_id,guard);return events

def level_up(path,owner,payload,operation,account_id,guard):
 from els_server.protocol.raid_economy_protocol import level_ack,weapon_point
 from els_server.storage.item_instances import remove
 if len(payload)!=16:raise ValueError('Native adjust point use length')
 index,uid,count=struct.unpack('>iQi',payload)
 if index!=5 or not 0<uid<2**63 or count!=1:raise ValueError('Native Barkat point up source/count')
 owner,digest=_identity(owner,0xc0b,payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');authorize(db,owner,account_id,guard)
  old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
  if old is not None:
   events=_updates(current_changes(db,operation,owner,0xc0b,old,before))+[level_ack()];prepare_events(events);authorize(db,owner,account_id,guard);return events
  points,generation=state.progress(db,owner,'barkat');level=rules.level('barkat',points)
  if level>=15:raise ValueError('Barkat weapon pity is already at original maximum level')
  row=rules.adjust('barkat')['DropLevel'][str(level+1)];cost=row['2']
  item=next((i for i in before if i['uid']==uid),None)
  if item is None or item['template']!=136181 or item['group']!=4 or item['count']<cost:raise ValueError('Barkat heart owned instance/count')
  require_current(item);require_unlocked(item);position=(item['group'],item['slot'])
  if item['count']==cost:remove(db,owner,item)
  else:db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=?',(cost,uid,owner))
  state.ensure(db);state.set_progress(db,owner,'barkat',row['3'],generation)
  after=load_items(db,owner);current=next((i for i in after if i['uid']==uid),None)
  events=_updates([(position,current)])+[level_ack(items=()if current is None else(current,)),weapon_point(5,row['3'])];prepare_events(events)
  if balance['revision']>=2**63-1:raise ValueError('Barkat point-up revision overflow')
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,));_commit(db,operation,digest,owner,0xc0b,[position],before,after)
  authorize(db,owner,account_id,guard);return events
