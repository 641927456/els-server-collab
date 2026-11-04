"""Own unexpanded room layouts; furniture remains an owned inventory instance."""
from contextlib import closing
from pathlib import Path
import hashlib,sqlite3,time
from els_server.domain.furniture_rules import validate_layout,TEMPLATES
from els_server.protocol.housing_layout_messages import LAYOUT,REQUEST,encode,decode,save_ack,empty_layout
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import housing_rooms,housing_access
from els_server.storage.inventory_state import load_items
WRITES_ENABLED=True
TABLE='character_housing_layouts_v1'
RECEIPTS='housing_layout_receipts'

def snapshot(db,owner,account,*,now=None):
 housing_access.owner(db,owner,account)
 if not housing_rooms.exists(db,TABLE):return None
 row=db.execute('SELECT account_id,version,payload,revision,updated_at FROM character_housing_layouts_v1 WHERE owner=?',(owner,)).fetchone()
 if row is None:return None
 if(row[:2]!=(account,1)or type(row[2])is not bytes or any(type(v)is not int or not 0<v<2**63 for v in row[3:])):raise ValueError('Unknown saved housing layout')
 layout=decode(LAYOUT,row[2]);validate_layout(layout,load_items(db,owner),now=now)
 return dict(layout=layout,revision=row[3],updated_at=row[4])

def project(db,owner,account,value,*,now=None):
 state=snapshot(db,owner,account,now=now)
 if state is not None:
  #0F7 is the native preset map. Base preset0 is the sole current allowance.
  value['0f7']=[(0,state['layout'])]
 return value

def save(path,owner,account,payload,operation,generation,admission,guard,*,now=None):
 request=decode(REQUEST,payload);legacy,new,grid,floor,expansion,preset=request
 if preset not in(-1,0):raise ValueError('Furniture unqualified preset')
 layout=(legacy,new,grid,floor,expansion)
 if not callable(guard)or type(operation)is not str or not 1<=len(operation)<=200:raise ValueError('Furniture current writer')
 digest=hashlib.sha256(payload).hexdigest();stamp=int(time.time())if now is None else now
 if type(stamp)is not int or not 0<stamp<2**63:raise ValueError('Furniture saved time')
 with closing(sqlite3.connect(Path(path),timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db)
  from els_server.storage.item_actor import require_active_character
  require_active_character(db,owner);housing_access.owner(db,owner,account)
  access=housing_access.snapshot(db,owner,account)
  if access is None or not access['registered_at']<=stamp<access['expires_at']:raise ValueError('Furniture current housing access')
  row=db.execute('SELECT owner,account_id,generation FROM housing_room_admissions WHERE operation_id=?',(admission,)).fetchone()
  room=housing_rooms.snapshot(db,owner,account)
  if row!=(owner,account,generation)or room is None or room['generation']!=generation:raise ValueError('Furniture durable admission changed')
  old=db.execute('SELECT owner,account_id,request_hash FROM housing_layout_receipts WHERE operation_id=?',(operation,)).fetchone()if housing_rooms.exists(db,RECEIPTS)else None
  state=snapshot(db,owner,account,now=stamp)
  if old is not None:
   if old!=(owner,account,digest)or state is None:raise ValueError('Furniture receipt collision')
   answer=[save_ack(state['layout'])]
   for e in answer:encode_event(e)
   guard(db);return answer
  if not WRITES_ENABLED:raise ValueError('Furniture writer held')
  before=load_items(db,owner);validate_layout(layout,before,mutating=True,now=stamp)
  revision=1 if state is None else state['revision']+1
  if revision>=2**63:raise ValueError('Furniture revision bound')
  db.execute('CREATE TABLE IF NOT EXISTS character_housing_layouts_v1 (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version=1),payload BLOB NOT NULL,revision INTEGER NOT NULL CHECK(revision>0),updated_at INTEGER NOT NULL CHECK(updated_at>0))')
  db.execute('CREATE TABLE IF NOT EXISTS housing_layout_receipts (operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,request_hash TEXT NOT NULL,revision INTEGER NOT NULL,created_at INTEGER NOT NULL)')
  db.execute('INSERT INTO character_housing_layouts_v1 VALUES (?,?,1,?,?,?) ON CONFLICT(owner)DO UPDATE SET payload=excluded.payload,revision=excluded.revision,updated_at=excluded.updated_at',(owner,account,encode(LAYOUT,layout),revision,stamp))
  db.execute('INSERT INTO housing_layout_receipts VALUES (?,?,?,?,?,?)',(operation,owner,account,digest,revision,stamp))
  answer=[save_ack(layout)]
  for e in answer:encode_event(e)
  guard(db)
  if not WRITES_ENABLED or load_items(db,owner)!=before or snapshot(db,owner,account,now=stamp)['layout']!=layout:raise ValueError('Furniture changed before commit')
  return answer
