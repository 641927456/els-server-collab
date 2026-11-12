"""Owned per-floor layouts; original floor0 records remain readable."""
from contextlib import closing
from pathlib import Path
import hashlib,sqlite3,time
from els_server.domain.furniture_rules import validate_layout
from els_server.domain.housing_pet_rules import mat
from els_server.protocol.housing_layout_messages import LAYOUT,REQUEST,encode,decode,save_ack,empty_layout
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import housing_rooms,housing_access
from els_server.storage.inventory_state import load_items
WRITES_ENABLED=True
TABLE='character_housing_floor_layouts_v2'
LEGACY_TABLE='character_housing_layouts_v1'
RECEIPTS='housing_layout_receipts'


def states(db,owner,account,*,now=None):
 housing_access.owner(db,owner,account);result={};items=load_items(db,owner)
 if housing_rooms.exists(db,TABLE):
  for floor,aid,version,payload,revision,stamp in db.execute('SELECT floor,account_id,version,payload,revision,updated_at FROM '+TABLE+' WHERE owner=? ORDER BY floor',(owner,)):
   if (aid,version)!=(account,2)or not 0<=floor<=2 or type(payload)is not bytes or any(type(v)is not int or not 0<v<2**63 for v in(revision,stamp)):raise ValueError('Unknown saved housing floor layout')
   layout=decode(LAYOUT,payload)
   if layout[4]!=floor:raise ValueError('Saved housing floor key mismatch')
   result[floor]=dict(layout=layout,revision=revision,updated_at=stamp)
 if 0 not in result and housing_rooms.exists(db,LEGACY_TABLE):
  row=db.execute('SELECT account_id,version,payload,revision,updated_at FROM '+LEGACY_TABLE+' WHERE owner=?',(owner,)).fetchone()
  if row is not None:
   if row[:2]!=(account,1)or type(row[2])is not bytes or any(type(v)is not int or not 0<v<2**63 for v in row[3:]):raise ValueError('Unknown saved housing layout')
   layout=decode(LAYOUT,row[2])
   # The old writer admitted only floor0 and its ctor-1 empty form.
   if layout[3]!=0 or layout[4]not in(-1,0):raise ValueError('Unknown legacy housing floor')
   result[0]=dict(layout=(*layout[:4],0),revision=row[3],updated_at=row[4],legacy_floor_locations=True)
 validate_set(result,items,now=now)
 return result


def validate_set(states,items,*,mutating_floor=None,now=None):
 used=set();mats=[]
 for floor,state in sorted(states.items()):
  layout=state['layout'];validate_layout(layout,items,mutating=floor==mutating_floor,now=now,legacy_floor_locations=state.get('legacy_floor_locations',False))
  uids={k for rows in layout[:2]for k,v in rows}
  if used&uids:raise ValueError('One owned furniture instance cannot occupy two floors')
  used.update(uids)
  target=mat(layout)
  if target is not None:mats.append(target)
 if len(mats)>1:raise ValueError('Housing permits one pet mat across floors')


def snapshot(db,owner,account,*,now=None,floor=0):return states(db,owner,account,now=now).get(floor)


def project(db,owner,account,value,*,now=None):
 room=housing_rooms.snapshot(db,owner,account);saved=states(db,owner,account,now=now)
 if room is None:
  if saved:raise ValueError('Housing floor layout has no room')
  return value
 allowed={floor for floor,pair in room['layout']}
 if set(saved)-allowed:raise ValueError('Saved layout uses an unowned floor')
 #0F7 is the per-floor map; final1C5 holds native preset summaries.
 value['0f7']=[(floor,saved[floor]['layout']if floor in saved else empty_layout(floor))for floor in sorted(allowed)]
 return value


def save(path,owner,account,payload,operation,generation,admission,guard,*,now=None,notify=None):
 legacy,new,grid,reserved,floor,selected=decode(REQUEST,payload)
 layout=(legacy,new,grid,reserved,floor)
 if not callable(guard)or type(operation)is not str or not 1<=len(operation)<=200:raise ValueError('Furniture current writer')
 digest=hashlib.sha256(payload).hexdigest()
 with closing(sqlite3.connect(Path(path),timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db)
  stamp=int(time.time())if now is None else now
  if type(stamp)is not int or not 0<stamp<2**63:raise ValueError('Furniture saved time')
  from els_server.storage.housing_expansions import require_room,write_floors
  room=require_room(db,owner,account,generation,admission,stamp);floors=dict(room['layout'])
  if floor not in floors or type(selected)is not int or not 0<=selected<=floors[floor][0]:raise ValueError('Furniture unowned floor or size')
  old=db.execute('SELECT owner,account_id,request_hash FROM housing_layout_receipts WHERE operation_id=?',(operation,)).fetchone()if housing_rooms.exists(db,RECEIPTS)else None
  saved=states(db,owner,account,now=stamp);state=saved.get(floor)
  if old is not None:
   if old!=(owner,account,digest)or state is None:raise ValueError('Furniture receipt collision')
   answer=[save_ack(state['layout'],maximum=floors[floor][0],selected=floors[floor][1])]
   for e in answer:encode_event(e)
   guard(db);return answer
  if not WRITES_ENABLED:raise ValueError('Furniture writer held')
  before=load_items(db,owner);revision=1 if state is None else state['revision']+1
  if revision>=2**63:raise ValueError('Furniture revision bound')
  saved[floor]=dict(layout=layout,revision=revision,updated_at=stamp)
  validate_set(saved,before,mutating_floor=floor,now=stamp)
  from els_server.storage.housing_pets import validate_layout as validate_pet_mat
  pet_layout=next((v['layout']for v in saved.values()if mat(v['layout'])is not None),layout)
  validate_pet_mat(db,owner,pet_layout)
  db.execute('CREATE TABLE IF NOT EXISTS character_housing_floor_layouts_v2 (owner INTEGER NOT NULL REFERENCES characters(uid),floor INTEGER NOT NULL CHECK(floor BETWEEN 0 AND 2),account_id INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version=2),payload BLOB NOT NULL,revision INTEGER NOT NULL CHECK(revision>0),updated_at INTEGER NOT NULL CHECK(updated_at>0),PRIMARY KEY(owner,floor))')
  db.execute('CREATE TABLE IF NOT EXISTS housing_layout_receipts (operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,request_hash TEXT NOT NULL,revision INTEGER NOT NULL,created_at INTEGER NOT NULL)')
  db.execute('INSERT INTO character_housing_floor_layouts_v2 VALUES (?,?,?,2,?,?,?) ON CONFLICT(owner,floor)DO UPDATE SET payload=excluded.payload,revision=excluded.revision,updated_at=excluded.updated_at',(owner,floor,account,encode(LAYOUT,layout),revision,stamp))
  floors[floor]=(floors[floor][0],selected);write_floors(db,owner,account,floors)
  db.execute('INSERT INTO housing_layout_receipts VALUES (?,?,?,?,?,?)',(operation,owner,account,digest,revision,stamp))
  from els_server.storage.housing_achievements import update as achievements
  answer=[save_ack(layout,maximum=floors[floor][0],selected=selected)]+achievements(db,owner,account,stamp)
  for e in answer:encode_event(e)
  guard(db)
  if not WRITES_ENABLED or load_items(db,owner)!=before or snapshot(db,owner,account,now=stamp,floor=floor)['layout']!=layout:raise ValueError('Furniture changed before commit')
  if notify is not None:notify(db,layout,selected)
  return answer
