"""Approved16/+8/max1064; held282600 or60 saved guild coins, master only.

The complete bank consumer/scene is still a qualification gate, not claimed by
this capacity producer. Lazy schema participates in the caller's writer.
"""
from contextlib import closing
import sqlite3,time
from els_server.protocol import guild_bank_capacity_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import guild_coin_state as coin
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.npc_trade import balances
WRITES_ENABLED=True
TABLE='native_guild_bank_expansions_v1'

def rows(db,guild):
 if not coin._exists(db,TABLE):return[]
 rows=db.execute('SELECT operation,request_hash,owner,account_id,item_uid,ticket,before_slots,after_slots,coin_cost,created_at,version FROM '+TABLE+' WHERE guild_id=? ORDER BY after_slots',(guild,)).fetchall()
 expected=16
 for op,digest,owner,account,uid,ticket,before,after,cost,stamp,version in rows:
  if(type(op)is not str or not 1<=len(op)<=160 or type(digest)is not str or len(digest)!=64 or any(type(n)is not int for n in(owner,account,uid,ticket,before,after,cost,stamp,version))or owner<=0 or account<=0 or stamp<=0 or ticket not in(0,1)or uid!=0 and ticket==0 or ticket==1 and not 0<uid<2**63 or before!=expected or after!=before+8 or after>1064 or cost!=(0 if ticket else 60)or version!=1):raise ValueError('Changed guild bank capacity ledger')
  receipt=db.execute('SELECT request_hash,owner,kind FROM inventory_action_receipts WHERE operation_id=?',(op,)).fetchone()if coin._exists(db,'inventory_action_receipts')else None
  if receipt!=(digest,owner,0x526):raise ValueError('Guild expansion lacks actual mutation receipt')
  expected=after
 return rows

def snapshot(db,guild):return 16+8*len(rows(db,guild))

def _schema(db):
 db.execute('''CREATE TABLE IF NOT EXISTS native_guild_bank_expansions_v1(operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,guild_id INTEGER NOT NULL REFERENCES native_guilds(id),owner INTEGER NOT NULL,account_id INTEGER NOT NULL,item_uid INTEGER NOT NULL,ticket INTEGER NOT NULL,before_slots INTEGER NOT NULL,after_slots INTEGER NOT NULL,coin_cost INTEGER NOT NULL,created_at INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version=1),UNIQUE(guild_id,after_slots))''')

def read(path,owner,account,guard):
 with closing(sqlite3.connect(path,timeout=10))as db:
  db.execute('BEGIN');saved=coin.authority(db,owner,account,guard);coin.snapshot(db,saved['id']);from els_server.storage.guild_bank_items import overview
  answer=overview(db,saved,owner,int(time.time()));encode_event(answer)
  if coin.authority(db,owner,account,guard)!=saved:raise ValueError('Guild overview late member changed')
  return[answer]

def perform(path,owner,account,payload,operation,guard,*,now=None):
 uid,ticket=wire.request(payload);owner,digest=_identity(owner,0x526,payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');saved=coin.authority(db,owner,account,guard);guild=saved['id'];capacity=snapshot(db,guild);value=coin.snapshot(db,guild)
  if saved['master_uid']!=owner or saved['grade']!=1:raise ValueError('Guild expansion current master only')
  before=load_items(db,owner);money=balances(db,owner);old=_previous(db,operation,digest)
  if old is not None:
   row=db.execute('SELECT request_hash,guild_id,owner,account_id,item_uid,ticket FROM '+TABLE+' WHERE operation=?',(operation,)).fetchone()if coin._exists(db,TABLE)else None
   if row!=(digest,guild,owner,account,uid,ticket):raise ValueError('Guild expansion replay source changed')
   answer=[wire.expanded(uid,value,ticket,current_changes(db,operation,owner,0x526,old,before)),_overview(db,saved,owner,now)]
   for e in answer:encode_event(e)
   if coin.authority(db,owner,account,guard)!=saved:raise ValueError('Guild expansion replay member changed')
   return answer
  if not WRITES_ENABLED or capacity>=1064 or money['revision']>=2**63-1:raise ValueError('Guild expansion disabled/full/revision')
  stamp=int(time.time())if now is None else now
  if type(stamp)is not int or stamp<=0:raise ValueError('Guild expansion server clock')
  positions=[]
  if ticket:
   item=next((i for i in before if i['uid']==uid),None)
   if item is None or(item['template'],item['metadata'],item['group'])!=(282600,0,4)or item.get('sealed',False)or item.get('seal_count',0):raise ValueError('Guild expansion held original ticket')
   from els_server.domain.item_expiration import require_current
   from els_server.domain.item_locks import require_unlocked
   require_current(item,now=stamp);require_unlocked(item,now=stamp);positions=[(item['group'],item['slot'])]
   if item['count']==1:
    from els_server.storage.item_instances import remove
    remove(db,owner,item)
   elif db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=?AND uid=?AND count=?',(owner,uid,item['count'])).rowcount!=1:raise ValueError('Guild ticket count changed')
  elif value<60:raise ValueError('Guild expansion saved coin shortage')
  _schema(db)
  db.execute('INSERT INTO '+TABLE+' VALUES(?,?,?,?,?,?,?,?,?,?,?,1)',(operation,digest,guild,owner,account,uid,ticket,capacity,capacity+8,0 if ticket else 60,stamp))
  if not ticket:
   if db.execute('UPDATE native_guild_coin_v1 SET balance=balance-60,revision=revision+1 WHERE guild_id=?AND balance=?',(guild,value)).rowcount!=1:raise ValueError('Guild expansion currency changed')
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};_commit(db,operation,digest,owner,0x526,positions,before,after)
  answer=[wire.expanded(uid,coin.snapshot(db,guild),ticket,[(p,current.get(p))for p in positions]),_overview(db,saved,owner,stamp)]
  for e in answer:encode_event(e)
  if coin.authority(db,owner,account,guard)!=saved or not WRITES_ENABLED or balances(db,owner)!=money or load_items(db,owner)!=after:raise ValueError('Guild expansion late authority changed')
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,));return answer

def _overview(db,saved,owner,now):
 from els_server.storage.guild_bank_items import overview
 return overview(db,saved,owner,int(time.time())if now is None else now)
