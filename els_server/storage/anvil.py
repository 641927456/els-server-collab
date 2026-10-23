"""One SQL transaction owns ED,hammer state,profession XP and anvil receipt.

Two new lazy optional schema definitions, no startup/read-time migration.
No inventory acquisition is performed and no existing receipt JSON is extended.
"""
from contextlib import closing
import hashlib,sqlite3,time
from els_server.domain.anvil_rules import integer,policy
from els_server.protocol.anvil_messages import request,state_wire,acknowledgement,notification
from els_server.protocol.profession_messages import ProfessionState,level_update
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.profession_state import require_owner,snapshot as profession_snapshot,replace as replace_profession
from els_server.storage.item_actor import require_active_character
from els_server.storage.npc_trade import balances,charge
from els_server.domain.profession_growth import advance_blacksmith
STATE_TABLE='profession_anvil_states'
RECEIPT_TABLE='profession_anvil_receipts'
def exists(db,name):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(name,)).fetchone())
def snapshot(db,uid,account_id):
 require_owner(db,uid,account_id)
 row=db.execute('SELECT account_id,hammers,ready_at,revision FROM profession_anvil_states WHERE uid=?',(uid,)).fetchone()if exists(db,STATE_TABLE)else None
 if row is None:return dict(hammers=0,ready_at=0,revision=0)
 if row[0]!=account_id:raise ValueError('Anvil persisted owner mismatch')
 state_wire(row[1],row[2]);integer(row[3],1,2**63-1,'Anvil revision')
 return dict(hammers=row[1],ready_at=row[2],revision=row[3])
def create_schema(db):
 if not db.in_transaction:raise ValueError('Anvil schema requires business transaction')
 db.execute('''CREATE TABLE IF NOT EXISTS profession_anvil_states(
 uid INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL,
 hammers INTEGER NOT NULL CHECK(hammers BETWEEN 0 AND 20),ready_at INTEGER NOT NULL CHECK(ready_at>=0),revision INTEGER NOT NULL CHECK(revision>0))''')
 db.execute('''CREATE TABLE IF NOT EXISTS profession_anvil_receipts(
 operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,
 ed_cost INTEGER NOT NULL CHECK(ed_cost>=0),hammer_gain INTEGER NOT NULL CHECK(hammer_gain=1),granted_xp INTEGER NOT NULL CHECK(granted_xp>=0),
 state_revision INTEGER NOT NULL,profession_revision INTEGER NOT NULL)''')
def authorize_now(authorize):
 if not callable(authorize)or not authorize():raise ValueError('Anvil current actor changed')
def response(ed,stored,xp=0,leveled=None):
 events=[acknowledgement(ed,stored['hammers'],stored['ready_at'],xp)]
 if leveled is not None:events.append(Event(0x201,kind=0x4c4,payload=level_update(leveled[0],leveled[1],{})))
 events.append(notification(stored['hammers'],stored['ready_at']))
 for event in events:encode_event(event)
 return events
def use(path,uid,account_id,payload,operation,*,authorize,prepare_replay=None,now=None):
 request(payload);integer(uid,1,2**63-1,'Anvil character');integer(account_id,1,2**63-1,'Anvil account')
 if not isinstance(operation,str)or not 1<=len(operation)<=160:raise ValueError('Anvil operation')
 if now is not None:integer(now,0,2**63-1-28800,'Anvil Unix now')
 digest=hashlib.sha256(str(uid).encode()+b':'+str(account_id).encode()+b':9B3:'+payload).hexdigest()
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  moment=int(time.time())if now is None else now;integer(moment,0,2**63-1-28800,'Anvil Unix now')
  authorize_now(authorize);require_active_character(db,uid);require_owner(db,uid,account_id)
  actor=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()
  if actor is None or type(actor[0])is not int or actor[0]<40:raise ValueError('Anvil level40 admission')
  growth=profession_snapshot(db,uid,account_id);state=ProfessionState(**growth['state']);rules=policy(state)
  stored=snapshot(db,uid,account_id);balance=balances(db,uid)
  prior=db.execute('SELECT request_hash,owner,account_id FROM profession_anvil_receipts WHERE operation=?',(operation,)).fetchone()if exists(db,RECEIPT_TABLE)else None
  if prior is not None:
   if prior!=(digest,uid,account_id):raise ValueError('Anvil operation identity collision')
   events=response(balance['ed'],stored)
   # Absolute account sync may take its own writer. Release this SQL transaction.
   db.rollback();authorize_now(authorize)
   if prepare_replay is not None:events=prepare_replay(events)
   for event in events:encode_event(event)
   authorize_now(authorize);return events
  if stored['hammers']>=rules['capacity']or stored['ready_at']>moment:raise ValueError('Anvil capacity or cooldown')
  if balance['ed']<rules['ed']:raise ValueError('Anvil insufficient ED')
  integer(stored['revision'],0,2**63-2,'Anvil CAS revision')
  next_profession,xp,leveled=advance_blacksmith(state,rules['requested_xp'])
  updated=dict(hammers=stored['hammers']+1,ready_at=moment+rules['cooldown_seconds'],revision=stored['revision']+1)
  # Encode every original packet before even lazy DDL or monetary mutation.
  events=response(balance['ed']-rules['ed'],updated,xp,(uid,next_profession)if leveled else None)
  authorize_now(authorize);create_schema(db)
  if stored['revision']==0:
   db.execute('INSERT INTO profession_anvil_states VALUES(?,?,?,?,?)',(uid,account_id,updated['hammers'],updated['ready_at'],updated['revision']))
  elif db.execute('UPDATE profession_anvil_states SET hammers=?,ready_at=?,revision=? WHERE uid=? AND account_id=? AND revision=?',(updated['hammers'],updated['ready_at'],updated['revision'],uid,account_id,stored['revision'])).rowcount!=1:raise ValueError('Anvil stale state')
  ed=charge(db,uid,balance,rules['ed']);assert ed==balance['ed']-rules['ed']
  saved=replace_profession(db,uid,account_id,growth['revision'],next_profession)if xp else growth
  db.execute('INSERT INTO profession_anvil_receipts VALUES(?,?,?,?,?,?,?,?,?)',(operation,digest,uid,account_id,rules['ed'],1,xp,updated['revision'],saved['revision']))
  authorize_now(authorize);return events
