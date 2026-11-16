"""Three current VIP coupons, original period consumer, approved character renewal."""
from contextlib import closing
from pathlib import Path
import sqlite3,time
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage import life_stamina as life
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.fishing_vip_messages import notice,deadline_text
from els_server.protocol.protocol_codec import encode_event

DAYS={135950:1,135957:10,135958:30}
TABLE='character_fishing_vip'
SQL='CREATE TABLE character_fishing_vip (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),expires_at INTEGER NOT NULL CHECK(expires_at>0),updated_at INTEGER NOT NULL CHECK(updated_at>0))'
WRITES_ENABLED=True

def snapshot(db,owner,account):
 from els_server.storage.profession_state import require_owner
 require_owner(db,owner,account)
 schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()
 if schema is None:return 0
 if schema!=(SQL,):raise ValueError('Unknown FishingVIP schema')
 row=db.execute('SELECT account_id,expires_at,updated_at FROM character_fishing_vip WHERE owner=?',(owner,)).fetchone()
 if row is None:return 0
 if row[0]!=account or any(type(v)is not int or v<=0 for v in row[1:])or not 0<row[1]-row[2]<=90*86400:raise ValueError('FishingVIP saved entitlement')
 deadline_text(row[1]);return row[1]

def active(db,owner,account,stamp):
 if type(stamp)not in(int,float)or stamp<0:raise ValueError('FishingVIP authority clock')
 return snapshot(db,owner,account)>stamp

def use(path,owner,account,payload,operation,guard,*,now=None):
 source=use_request(payload);owner,digest=_identity(owner,0x219,b'FishingVIP:'+payload,operation)
 if not callable(guard):raise ValueError('FishingVIP actor guard')
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db);life.owner(db,owner,account)
  before=load_items(db,owner);old=_previous(db,operation,digest);expiry=snapshot(db,owner,account)
  balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()
  if balance is None or type(balance[0])is not int or not 0<=balance[0]<2**63:raise ValueError('FishingVIP ED read')
  if old is not None:
   import json
   proof=json.loads(db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()[0]);item=next((i for i in proof if i['uid']==source),None)
   if item is None or item['template']not in DAYS or not expiry:raise ValueError('FishingVIP receipt proof')
   answer=[use_ack(current_changes(db,operation,owner,0x219,old,before),item['template'],balance[0]),notice(expiry)]
   for event in answer:encode_event(event)
   guard(db);return answer
  if not WRITES_ENABLED:raise ValueError('FishingVIP writer held')
  item=next((i for i in before if i['uid']==source),None)
  if item is None or item['template']not in DAYS:return None
  stamp=int(time.time())if now is None else now
  if type(stamp)is not int or stamp<=0:raise ValueError('FishingVIP use clock')
  if life.snapshot(db,owner,account)['current']==0:raise ValueError('FishingVIP life exhausted')
  if item['metadata']!=0 or item['group']!=4 or not 1<=item['count']<2**31:raise ValueError('FishingVIP source shape')
  from els_server.domain.item_expiration import require_current
  from els_server.domain.item_locks import require_unlocked
  require_current(item,now=stamp);require_unlocked(item,now=stamp)
  if item.get('sealed',False)or item.get('seal_count',0):raise ValueError('FishingVIP sealed source')
  updated=max(stamp,expiry)+DAYS[item['template']]*86400
  if updated>stamp+90*86400:raise ValueError('FishingVIP90day cap')
  deadline_text(updated)
  if not db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(TABLE,)).fetchone():db.execute(SQL)
  db.execute('INSERT INTO character_fishing_vip VALUES(?,?,?,?)ON CONFLICT(owner)DO UPDATE SET expires_at=excluded.expires_at,updated_at=excluded.updated_at',(owner,account,updated,stamp))
  remaining=item['count']-1
  if remaining:
   if db.execute('UPDATE inventory_items SET count=? WHERE owner=?AND uid=?AND count=?',(remaining,owner,source,item['count'])).rowcount!=1:raise ValueError('FishingVIP source compare-and-set')
  else:remove(db,owner,item)
  after=load_items(db,owner);position=(item['group'],item['slot']);current=next((i for i in after if i['uid']==source),None)
  answer=[use_ack([(position,current)],item['template'],balance[0]),notice(updated)]
  for event in answer:encode_event(event)
  guard(db)
  if not WRITES_ENABLED or snapshot(db,owner,account)!=updated or load_items(db,owner)!=after:raise ValueError('FishingVIP late state changed')
  _commit(db,operation,digest,owner,0x219,[position],before,after);return answer
