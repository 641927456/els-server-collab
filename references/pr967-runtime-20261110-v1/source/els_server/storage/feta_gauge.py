"""Owned coupon, accessory3 progress, paired receipt and encoding in one SQL."""
from pathlib import Path
from contextlib import closing
import json,sqlite3,struct,time
from els_server.domain.feta_gauge_rules import _GaugeAuthority,catalog,plain,DATA_SHA
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.resonance_state import owner as require_owner
from els_server.storage.reward_state import validate_balances
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage import raid_economy_state as state
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.protocol_codec import encode_event
WRITER_ENABLED=True
TABLE='feta_gauge_use_receipts'

def prior(db,operation):
 if not state.exists(db,TABLE):return None
 return db.execute('SELECT account_id,owner,item_uid,before_points,after_points,generation,policy_sha FROM feta_gauge_use_receipts WHERE operation=?',(operation,)).fetchone()

def recognizes(path,owner,payload,operation):
 if type(payload)is not bytes or len(payload)<8:return False
 uid=struct.unpack_from('>Q',payload)[0]
 if not 0<uid<2**63:return False
 try:
  with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
   row=db.execute('SELECT template FROM inventory_items WHERE uid=? AND owner=?',(uid,owner)).fetchone()
   return bool(row==(30880,)or prior(db,operation))
 except sqlite3.Error:return False

def context(db,owner,account,authorize):
 if(type(authorize)is not _GaugeAuthority or authorize.owner!=owner or authorize.account_id!=account
 or not WRITER_ENABLED or not db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()!=(1,)
 or authorize()is not True):raise ValueError('Gauge exact current writer authority')
 files=db.execute('PRAGMA database_list').fetchall()
 if len(files)!=1 or files[0][1]!='main' or Path(files[0][2]).resolve()!=authorize.path:raise ValueError('Gauge exact original SQL')
 require_owner(db,owner,account);require_active_character(db,owner)

def history(db,operation,owner,account,uid,positions):
 row=prior(db,operation)
 if(row is None or row[:3]!=(account,owner,uid)or row[6]!=DATA_SHA
 or not 0<=row[3]<100 or row[4]!=min(100,row[3]+2)or not 0<=row[5]<2**31):raise ValueError('Gauge paired original history')
 receipt=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
 if receipt is None or receipt[:2]!=(owner,0x219):raise ValueError('Gauge paired inventory history')
 try:
  before=json.loads(receipt[2]);after=json.loads(receipt[3]);b={i['uid']:i for i in before};a={i['uid']:i for i in after}
  if len(b)!=len(before)or len(a)!=len(after)or uid not in b or not plain(b[uid]):raise ValueError('Gauge historical owned item')
  old=b[uid];new=a.get(uid)
  if new is not None and({k:v for k,v in new.items()if k!='count'}!={k:v for k,v in old.items()if k!='count'}or new['count']!=old['count']-1):raise ValueError('Gauge historical decrement')
  if new is None and old['count']!=1:raise ValueError('Gauge historical removal')
  if {k:v for k,v in b.items()if k!=uid}!={k:v for k,v in a.items()if k!=uid}or list(positions)!=[(old['group'],old['slot'])]:raise ValueError('Gauge changed unrelated inventory')
 except(KeyError,TypeError,json.JSONDecodeError)as e:raise ValueError('Gauge corrupt historical receipt')from e
 current=state.progress(db,owner,'accessory:3')
 if current[1]<row[5]or current[1]==row[5]and current[0]<row[4]:raise ValueError('Gauge historical progress regressed')
 return row

def snapshot(db,owner):
 from els_server.domain.raid_reward_flow import snapshot as original
 from els_server.protocol.raid_economy_protocol import point_snapshot
 values,weapons=original(db,owner)
 return point_snapshot(values,db=db,owner=owner)

def perform(path,owner,account_id,payload,operation,*,authorize,now=None,encode=use_ack,notice=snapshot):
 uid=use_request(payload);p=catalog()
 if(type(authorize)is not _GaugeAuthority or authorize.operation!=operation or authorize.payload!=payload
 or type(account_id)is not int or not 1<=account_id<2**63):raise ValueError('Gauge exact request authority')
 if now is not None and(type(now)is not int or not 0<=now<2**40):raise ValueError('Gauge bounded original clock')
 owner,digest=_identity(owner,0x219,struct.pack('>Q',account_id)+payload,operation)
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');context(db,owner,account_id,authorize)
  if now is None:now=int(time.time())
  wallet=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone());before=load_items(db,owner);old=_previous(db,operation,digest)
  if old is not None:
   history(db,operation,owner,account_id,uid,old)
   changes=current_changes(db,operation,owner,0x219,old,before)
   events=[encode(changes,ed=wallet['ed']),notice(db,owner)]
   for e in events:encode_event(e)
   context(db,owner,account_id,authorize);return events
  if prior(db,operation)is not None:raise ValueError('Gauge unpaired retry')
  item=next((i for i in before if i['uid']==uid),None)
  if item is None or not plain(item):raise ValueError('Gauge finite eligible owned instance')
  from els_server.domain.item_expiration import require_current
  from els_server.domain.item_locks import require_unlocked
  require_current(item,now=now);require_unlocked(item,now=now)
  points,generation=state.progress(db,owner,p['progress'])
  if points>=p['maximum']:raise ValueError('Gauge full; do not consume')
  state.ensure(db);position=(item['group'],item['slot'])
  if item['count']==1:
   from els_server.storage.item_instances import remove
   remove(db,owner,item)
  elif db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',(uid,owner,item['count'])).rowcount!=1:raise ValueError('Gauge inventory CAS')
  state.set_progress(db,owner,p['progress'],min(p['maximum'],points+p['gain']),generation)
  db.execute('CREATE TABLE IF NOT EXISTS feta_gauge_use_receipts(operation TEXT PRIMARY KEY,account_id INTEGER NOT NULL,owner INTEGER NOT NULL,item_uid INTEGER NOT NULL,before_points INTEGER NOT NULL,after_points INTEGER NOT NULL,generation INTEGER NOT NULL,policy_sha TEXT NOT NULL)')
  db.execute('INSERT INTO feta_gauge_use_receipts VALUES(?,?,?,?,?,?,?,?)',(operation,account_id,owner,uid,points,min(100,points+2),generation,DATA_SHA))
  after=load_items(db,owner);current=next((i for i in after if(i['group'],i['slot'])==position),None)
  events=[encode([(position,current)],30880,wallet['ed']),notice(db,owner)]
  for e in events:encode_event(e)
  if db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()!=tuple(wallet[k]for k in('ed','experience','revision')):raise ValueError('Gauge zero-fee wallet preservation')
  context(db,owner,account_id,authorize);_commit(db,operation,digest,owner,0x219,[position],before,after)
  history(db,operation,owner,account_id,uid,[position]);context(db,owner,account_id,authorize)
  return events
