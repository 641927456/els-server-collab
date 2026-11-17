"""Source-bound guild storage; complete items use the shared container mover."""
from contextlib import closing
import json,sqlite3,time
from els_server.domain.guild_bank_rules import require_item,period
from els_server.domain.inventory_items import validate_item,TEMPLATE_MAX_STACKS,TEMPLATE_BAG_GROUPS
from els_server.domain.item_expiration import expired
from els_server.protocol import guild_bank_transfer_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import guild_coin_state as coin,guild_bank_capacity as capacity
from els_server.storage.inventory_state import load_items,InventoryFull
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import insert,remove,next_uid
from els_server.storage.npc_trade import balances
WRITES_ENABLED=True
TABLE='native_guild_bank_items_v1'
ACTIONS='native_guild_bank_transfers_v1'

def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))

def _schema(db):
 db.execute('''CREATE TABLE IF NOT EXISTS native_guild_bank_items_v1(uid INTEGER PRIMARY KEY,guild_id INTEGER NOT NULL REFERENCES native_guilds(id),slot INTEGER NOT NULL,item_json TEXT NOT NULL,source_operation TEXT NOT NULL,UNIQUE(guild_id,slot))''')
 db.execute('''CREATE TABLE IF NOT EXISTS native_guild_bank_transfers_v1(operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,guild_id INTEGER NOT NULL REFERENCES native_guilds(id),owner INTEGER NOT NULL,account_id INTEGER NOT NULL,kind INTEGER NOT NULL,template INTEGER NOT NULL,quantity INTEGER NOT NULL,created_at INTEGER NOT NULL,before_bank_json TEXT NOT NULL,after_bank_json TEXT NOT NULL,version INTEGER NOT NULL CHECK(version=1))''')

def load(db,guild,*,now):
 tables=[coin._exists(db,t)for t in(TABLE,ACTIONS)]
 if not any(tables):return[]
 if not all(tables):raise ValueError('Partial guild bank item schema')
 result=[];limit=capacity.snapshot(db,guild)
 for uid,slot,raw,source in db.execute('SELECT uid,slot,item_json,source_operation FROM '+TABLE+' WHERE guild_id=? ORDER BY slot',(guild,)):
  from els_server.domain.cartridge_registration_rules import _unique_json,non_authority,require_unbound
  item=validate_item(non_authority(_unique_json(raw)),container='guild_bank');require_unbound(db,uid)
  if item['uid']!=uid or type(slot)is not int or not 0<=slot<limit:raise ValueError('Guild bank persisted UID/slot')
  row=db.execute('SELECT guild_id,after_bank_json,version,request_hash,owner,kind FROM '+ACTIONS+' WHERE operation=?',(source,)).fetchone()
  if row is None or row[0]!=guild or row[2]!=1 or not any(e==dict(slot=slot,item=item)for e in json.loads(row[1])):raise ValueError('Guild bank item lacks actual producer')
  receipt=db.execute('SELECT request_hash,owner,kind FROM inventory_action_receipts WHERE operation_id=?',(source,)).fetchone()
  if receipt!=(row[3],row[4],row[5])or row[5]not in(0x50a,0x50c):raise ValueError('Guild bank source receipt changed')
  for other in('inventory_items','private_bank_items','shared_bank_items'):
   if coin._exists(db,other)and db.execute('SELECT 1 FROM '+other+' WHERE uid=?',(uid,)).fetchone():raise ValueError('Guild bank UID duplicated in another container')
  if not expired(item,now=now):require_item(item,now=now,container='guild_bank')
  result.append(dict(slot=slot,item=item))
 return result

def counts(db,saved,owner,now):
 authority=saved['system']['authorities'][str(saved['grade'])]
 honor=saved['system']['member_details'].get(str(owner),{}).get('honor',0)
 limit=authority[4]if honor>=authority[5]else 0
 if not coin._exists(db,ACTIONS):return 0,limit
 stamps=db.execute('SELECT created_at FROM '+ACTIONS+' WHERE guild_id=?AND owner=?AND kind=?',(saved['id'],owner,0x50c)).fetchall()
 if any(type(t)is not int or t<=0 for t, in stamps):raise ValueError('Guild withdrawal clock source')
 return sum(period(t)==period(now)for t, in stamps),limit

def overview(db,saved,owner,now):
 from els_server.storage.guild_bank_history import snapshot as history
 history(db,saved['id'])
 entries=load(db,saved['id'],now=now);used,limit=counts(db,saved,owner,now)
 return wire.overview(capacity.snapshot(db,saved['id']),[e['item']for e in entries if not expired(e['item'],now=now)],used,limit)

def _put(db,guild,entries,operation):
 db.execute('DELETE FROM '+TABLE+' WHERE guild_id=?',(guild,))
 for entry in entries:
  item=entry['item'];db.execute('INSERT INTO '+TABLE+' VALUES(?,?,?,?,?)',(item['uid'],guild,entry['slot'],_json(item),operation))

def _stack_key(item):
 return {k:v for k,v in item.items()if k not in('uid','count','group','slot')}

def perform(path,owner,account,kind,payload,operation,guard,*,now=None):
 if kind not in(0x50a,0x50c):raise ValueError('Guild bank original transfer kind')
 uid,quantity,target=wire.request(payload);owner,digest=_identity(owner,kind,payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');saved=coin.authority(db,owner,account,guard)
  stamp=int(time.time())if now is None else now;period(stamp)
  guild=saved['id'];coin.snapshot(db,guild);_history(db,guild);entries=load(db,guild,now=stamp);before=load_items(db,owner);money=balances(db,owner);used,limit=counts(db,saved,owner,stamp);old=_previous(db,operation,digest)
  if old is not None:
   row=db.execute('SELECT request_hash,guild_id,owner,account_id,kind FROM '+ACTIONS+' WHERE operation=?',(operation,)).fetchone()if coin._exists(db,ACTIONS)else None
   if row!=(digest,guild,owner,account,kind):raise ValueError('Guild bank replay changed source')
   emit=wire.deposited if kind==0x50a else wire.withdrawn
   answer=[emit([e['item']for e in entries if not expired(e['item'],now=stamp)],current_changes(db,operation,owner,kind,old,before),used,limit)]
   for e in answer:encode_event(e)
   if coin.authority(db,owner,account,guard)!=saved:raise ValueError('Guild transfer replay membership changed')
   return answer
  if not WRITES_ENABLED or money['revision']>=2**63-1:raise ValueError('Guild bank writer/revision')
  level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()
  if level is None or level[0]<70:raise ValueError('Original guild bank transfer minimum70')
  if kind==0x50c and used>=limit:raise ValueError('Approved guild withdrawal allowance')
  original=[dict(slot=e['slot'],item=dict(e['item']))for e in entries];entries=[e for e in entries if not expired(e['item'],now=stamp)];_schema(db);positions=[]
  if kind==0x50a:
   item=next((i for i in before if i['uid']==uid),None)
   if item is None:raise ValueError('Guild deposit owned source')
   item=require_item(item,now=stamp);quantity=quantity or item['count']
   if quantity>item['count']:raise ValueError('Guild deposit quantity')
   if target!=wire.NONE:raise ValueError('Original current deposit has no explicit merge target')
   merge=next((e for e in entries if TEMPLATE_MAX_STACKS[item['template']]>1 and _stack_key(e['item'])==_stack_key(item)and e['item']['count']+quantity<2**31),None)
   slots={e['slot']for e in entries};slot=next((n for n in range(capacity.snapshot(db,guild))if n not in slots),None)
   if merge is None and slot is None:raise InventoryFull('Guild bank is full')
   positions=[(item['group'],item['slot'])]
   if quantity==item['count']:moved=item;remove(db,owner,item)
   else:
    moved={**item,'uid':next_uid(db)if merge is None else uid,'count':quantity}
    if db.execute('UPDATE inventory_items SET count=count-? WHERE owner=?AND uid=?AND count=?',(quantity,owner,uid,item['count'])).rowcount!=1:raise ValueError('Guild deposit source changed')
   # Official enhancement transitions: entering guild storage resets both
   # per-item progress counters, while sockets, attributes and level persist.
   moved={k:v for k,v in moved.items()if k not in('enhancement_gauge','enhancement_guarantee')}
   if merge is None:entries.append(dict(slot=slot,item=validate_item(moved,container='guild_bank')))
   else:merge['item']=validate_item({**merge['item'],'count':merge['item']['count']+quantity},container='guild_bank')
  else:
   entry=next((e for e in entries if e['item']['uid']==uid),None)
   if entry is None:raise ValueError('Guild withdrawal current source')
   item=require_item(entry['item'],now=stamp,container='guild_bank');quantity=quantity or item['count']
   if quantity>item['count']:raise ValueError('Guild withdrawal quantity')
   if quantity>saved['system']['authorities'][str(saved['grade'])][6]:raise ValueError('Guild rank maximum items per withdrawal')
   from els_server.storage.bag_capacity import allowances
   group=TEMPLATE_BAG_GROUPS[item['template']];limits=allowances(db,owner);taken={i['slot']for i in before if i['group']==group}
   destination=None if target==wire.NONE else next((i for i in before if i['uid']==target),None)
   if target!=wire.NONE:
    if destination is None or destination['template']!=item['template']or destination['metadata']!=item['metadata']or destination['group']!=group or set(destination)-{'uid','template','metadata','count','group','slot'}or set(item)-{'uid','template','metadata','count','group','slot'}or destination['count']+quantity>TEMPLATE_MAX_STACKS[item['template']]:raise ValueError('Guild withdrawal exact plain merge target')
    positions=[(group,destination['slot'])]
    if db.execute('UPDATE inventory_items SET count=count+? WHERE owner=?AND uid=?AND count=?',(quantity,owner,target,destination['count'])).rowcount!=1:raise ValueError('Guild withdrawal merge changed')
   else:
    maximum=TEMPLATE_MAX_STACKS[item['template']];chunks=(quantity+maximum-1)//maximum
    slots=[n for n in range(limits[group])if n not in taken][:chunks]
    if len(slots)!=chunks:raise InventoryFull('Guild withdrawal bag is full')
    moved=[];remaining=quantity
    for index,slot in enumerate(slots):
     count=min(remaining,maximum);remaining-=count
     moved.append({**item,'uid':uid if quantity==item['count']and index==0 else next_uid(db),'count':count,'group':group,'slot':slot})
    positions=[(group,slot)for slot in slots]
   if quantity==item['count']:entries.remove(entry)
   else:entry['item']={**item,'count':item['count']-quantity}
   # Delete the old source row before reinserting a retained UID in a bag.
   if db.execute('DELETE FROM '+TABLE+' WHERE guild_id=?AND uid=?',(guild,uid)).rowcount!=1:raise ValueError('Guild withdrawal source changed')
   if target==wire.NONE:
    for chunk in moved:insert(db,owner,chunk)
  after=load_items(db,owner);_commit(db,operation,digest,owner,kind,positions,before,after)
  db.execute('INSERT INTO '+ACTIONS+' VALUES(?,?,?,?,?,?,?,?,?,?,?,1)',(operation,digest,guild,owner,account,kind,item['template'],quantity,stamp,_json(original),_json(entries)));_put(db,guild,entries,operation)
  from els_server.storage.guild_bank_history import record_transfer
  record_transfer(db,saved,owner,account,item['template'],quantity,0 if kind==0x50a else 1,operation,stamp)
  current={(i['group'],i['slot']):i for i in after};used,limit=counts(db,saved,owner,stamp);emit=wire.deposited if kind==0x50a else wire.withdrawn;answer=[emit([e['item']for e in entries],[(p,current.get(p))for p in positions],used,limit)]
  for e in answer:encode_event(e)
  if coin.authority(db,owner,account,guard)!=saved or not WRITES_ENABLED or balances(db,owner)!=money or load_items(db,owner)!=after or load(db,guild,now=stamp)!=sorted(entries,key=lambda e:e['slot']):raise ValueError('Guild bank late state changed')
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,));return answer

def _history(db,guild):
 from els_server.storage.guild_bank_history import snapshot
 snapshot(db,guild)
