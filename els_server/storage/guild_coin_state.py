"""Owned native coin -> guild counter and same-count seed ticket, one writer."""
from contextlib import closing
import sqlite3,time
from els_server.domain.guild_coin_rules import COIN,POLICY,definitions,plan
from els_server.protocol.guild_coin_messages import request,donated
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.guild_membership_state import snapshot as membership
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances
WRITES_ENABLED=True
def _exists(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(name,)).fetchone()is not None
def authority(db,owner,account,guard):
 if not db.in_transaction or not callable(guard):raise ValueError('Guild coin caller transaction')
 guard(db)
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.profession_state import require_owner
 require_active_character(db,owner);require_owner(db,owner,account)
 saved=membership(db,owner,account)
 if saved is None:raise ValueError('Guild coin actual membership required')
 definitions();return saved
def snapshot(db,guild):
 from els_server.storage.guild_bank_capacity import rows as expansions
 debits=[r for r in expansions(db,guild)if not r[5]]
 tables=('native_guild_coin_v1','native_guild_coin_donations_v1');present=[_exists(db,t)for t in tables]
 if not any(present):
  if debits:raise ValueError('Guild expansion debit lacks currency producer')
  return 0
 if not all(present):raise ValueError('Partial guild coin schema')
 row=db.execute('SELECT balance,revision,version FROM native_guild_coin_v1 WHERE guild_id=?',(guild,)).fetchone()
 history=db.execute('SELECT quantity FROM native_guild_coin_donations_v1 WHERE guild_id=?',(guild,)).fetchall()
 if row is None:
  if history or debits:raise ValueError('Guild coin ledger without counter')
  return 0
 if any(type(n)is not int or not 1<=n<=500 for n, in history)or row!=(sum(n for n, in history)-60*len(debits),len(history)+len(debits),1)or not 0<=row[0]<2**31:raise ValueError('Unknown or changed guild coin ledger')
 return row[0]
def read(path,owner,account,guard):
 with closing(sqlite3.connect(path,timeout=10))as db:
  db.execute('BEGIN');saved=authority(db,owner,account,guard);value=snapshot(db,saved['id']);authority(db,owner,account,guard);return value
def _schema(db):
 db.execute('''CREATE TABLE IF NOT EXISTS native_guild_coin_v1(guild_id INTEGER PRIMARY KEY REFERENCES native_guilds(id),balance INTEGER NOT NULL,revision INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version=1))''')
 db.execute('''CREATE TABLE IF NOT EXISTS native_guild_coin_donations_v1(operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,guild_id INTEGER NOT NULL REFERENCES native_guilds(id),owner INTEGER NOT NULL,account_id INTEGER NOT NULL,item_uid INTEGER NOT NULL,quantity INTEGER NOT NULL,created_at INTEGER NOT NULL)''')
def perform(path,owner,account,payload,operation,guard,*,now=None):
 item_uid,quantity=request(payload);owner,digest=_identity(owner,0x524,payload,operation)
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');saved=authority(db,owner,account,guard);guild=saved['id'];value=snapshot(db,guild)
  before=load_items(db,owner);old=_previous(db,operation,digest);money=balances(db,owner)
  if old is not None:
   row=db.execute('SELECT request_hash,guild_id,owner,account_id,item_uid,quantity FROM native_guild_coin_donations_v1 WHERE operation=?',(operation,)).fetchone()if _exists(db,'native_guild_coin_donations_v1')else None
   if row!=(digest,guild,owner,account,item_uid,quantity):raise ValueError('Guild coin replay source changed')
   answer=[donated(item_uid,quantity,value,current_changes(db,operation,owner,0x524,old,before))]
   for event in answer:encode_event(event)
   if authority(db,owner,account,guard)!=saved:raise ValueError('Guild coin replay membership changed')
   return answer
  if not WRITES_ENABLED or value+quantity>=2**31 or money['revision']>=2**63-1:raise ValueError('Guild coin writer/native counter bound')
  item=next((i for i in before if i['uid']==item_uid),None)
  if item is None or(item['template'],item['metadata'],item['group'])!=(COIN,2,4)or not quantity<=item['count']<=500 or item.get('sealed',False)or item.get('seal_count',0):raise ValueError('Guild coin owned native stack')
  stamp=int(time.time())if now is None else now
  if type(stamp)is not int or stamp<=0:raise ValueError('Guild coin server clock')
  from els_server.domain.item_expiration import require_current
  from els_server.domain.item_locks import require_unlocked
  require_current(item,now=stamp);require_unlocked(item,now=stamp)
  _schema(db)
  if item['count']==quantity:remove(db,owner,item)
  elif db.execute('UPDATE inventory_items SET count=count-? WHERE owner=?AND uid=?AND count=?',(quantity,owner,item_uid,item['count'])).rowcount!=1:raise ValueError('Guild coin count changed')
  from els_server.domain.raid_reward_items import _issue_source
  import uuid
  cap=_issue_source(db,owner,str(uuid.uuid5(uuid.NAMESPACE_URL,'guild-coin:'+operation)),'guild_donation',dict(policy=POLICY,template=COIN,owner=owner,guild_id=guild,uid=item_uid,quantity=quantity),plan(quantity),lambda writer:authority(writer,owner,account,guard)==saved)
  grants=grant_items(db,plan(quantity),owner,raid_reward_source=cap)
  db.execute('INSERT INTO native_guild_coin_donations_v1 VALUES(?,?,?,?,?,?,?,?)',(operation,digest,guild,owner,account,item_uid,quantity,stamp))
  db.execute('INSERT INTO native_guild_coin_v1 VALUES(?,?,1,1) ON CONFLICT(guild_id) DO UPDATE SET balance=excluded.balance,revision=revision+1',(guild,value+quantity))
  from els_server.storage.guild_bank_history import record_donation
  record_donation(db,saved,owner,account,quantity,operation,stamp)
  after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};positions=sorted({(item['group'],item['slot']),*[(i['group'],i['slot'])for i in grants]})
  answer=[donated(item_uid,quantity,snapshot(db,guild),[(p,current.get(p))for p in positions])]
  for event in answer:encode_event(event)
  if authority(db,owner,account,guard)!=saved or not WRITES_ENABLED or balances(db,owner)!=money or load_items(db,owner)!=after:raise ValueError('Guild coin late authority changed')
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,));_commit(db,operation,digest,owner,0x524,positions,before,after)
  return answer
