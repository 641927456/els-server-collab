"""Original D37 native preset description, with owned furniture/stage authority."""
from contextlib import closing
from pathlib import Path
import hashlib,sqlite3,time
from els_server.protocol import housing_preset_messages as wire
from els_server.protocol.housing_layout_messages import encode,decode
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import housing_access,housing_rooms,housing_expansions

TABLE='character_housing_presets_v1'
RECEIPTS='housing_preset_receipts'
WRITES_ENABLED=True


def validate(preset):
 from els_server.domain.bag_capacity import FURNITURE_CAPACITY
 from els_server.domain.furniture_rules import POSITION_TYPES,PET_TEMPLATES
 slot,name,stage,legacy,modern=preset
 if not name or not 0<=stage<=4 or not 1<=len(legacy)+len(modern)<=FURNITURE_CAPACITY:raise ValueError('Housing preset name/stage/size')
 skins=set();mats=0
 for free,rows in((False,legacy),(True,modern)):
  for row in rows:
   if free:
    reserved,template,position,xyz,last=row
    if reserved or template in PET_TEMPLATES:raise ValueError('Housing preset free-placement fields')
   else:position,template,x,y=row;xyz=(x,y,0)
   if template not in POSITION_TYPES or position not in POSITION_TYPES[template]or any(abs(v)>1000000 for v in xyz):raise ValueError('Housing preset native furniture fields')
   if position in(4,5,6):
    if position in skins:raise ValueError('Housing preset duplicate surface')
    skins.add(position)
   mats+=template in PET_TEMPLATES
 if mats>1:raise ValueError('Housing preset permits one pet mat')
 return preset


def snapshot(db,owner,account):
 housing_access.owner(db,owner,account)
 if not housing_rooms.exists(db,TABLE):return {}
 result={}
 for slot,aid,version,payload,revision,stamp in db.execute('SELECT slot,account_id,version,payload,revision,updated_at FROM '+TABLE+' WHERE owner=? ORDER BY slot',(owner,)):
  if aid!=account or version!=1 or type(slot)is not int or not 0<=slot<4 or type(payload)is not bytes or any(type(v)is not int or not 0<v<2**63 for v in(revision,stamp)):raise ValueError('Unknown housing preset saved format')
  preset=validate(decode(wire.PRESET,payload))
  if preset[0]!=slot:raise ValueError('Saved housing preset slot')
  result[slot]=dict(preset=preset,revision=revision,updated_at=stamp)
 if result and max(result)>housing_expansions.preset_expansions(db,owner,account):raise ValueError('Saved housing preset exceeds owned allowance')
 return result


def require_furniture(db,owner,preset,stamp):
 from collections import Counter
 from els_server.storage.inventory_state import load_items
 from els_server.domain.item_expiration import expired
 requested=Counter(row[1]for rows in preset[3:]for row in rows)
 owned=Counter(item['template']for item in load_items(db,owner)if(item['group'],item['metadata'],item['count'])==(25,0,1)and not item.get('sealed',False)and not expired(item,now=stamp))
 if requested-owned:raise ValueError('Housing preset requires current owned furniture quantities')


def save(path,owner,account,payload,operation,generation,admission,floor,guard,*,now=None):
 requested,rename=wire.request(payload);slot,name,stage,legacy,modern=requested
 if not callable(guard)or type(operation)is not str or not 1<=len(operation)<=200 or not 0<=slot<4:raise ValueError('Housing preset current request')
 validate(requested)
 digest=hashlib.sha256(payload).hexdigest()
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db)
  stamp=int(time.time())if now is None else now
  if type(stamp)is not int or not 0<stamp<2**63:raise ValueError('Housing preset time')
  room=housing_expansions.require_room(db,owner,account,generation,admission,stamp)
  floors=dict(room['layout'])
  if floor not in floors or slot>housing_expansions.preset_expansions(db,owner,account):raise ValueError('Housing preset unowned slot/floor')
  saved=snapshot(db,owner,account);current=saved.get(slot)
  old=db.execute('SELECT owner,account_id,request_hash,slot FROM '+RECEIPTS+' WHERE operation_id=?',(operation,)).fetchone()if housing_rooms.exists(db,RECEIPTS)else None
  if old is not None:
   if old!=(owner,account,digest,slot)or current is None:raise ValueError('Housing preset receipt collision')
   answer=[wire.acknowledgement(current['preset'])]
   for event in answer:encode_event(event)
   guard(db);return answer
  if not WRITES_ENABLED:raise ValueError('Housing preset writer held')
  if rename:
   if current is None or (stage,legacy,modern)!=current['preset'][2:]:raise ValueError('Housing preset rename requires current saved summary')
   preset=(slot,name,*current['preset'][2:])
  else:
   if stage>floors[floor][0]:raise ValueError('Housing preset requires an unlocked current-floor stage')
   require_furniture(db,owner,requested,stamp)
   preset=requested
  revision=1 if current is None else current['revision']+1
  if revision>=2**63:raise ValueError('Housing preset revision bound')
  db.execute('CREATE TABLE IF NOT EXISTS character_housing_presets_v1(owner INTEGER NOT NULL REFERENCES characters(uid),slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 3),account_id INTEGER NOT NULL,version INTEGER NOT NULL CHECK(version=1),payload BLOB NOT NULL,revision INTEGER NOT NULL CHECK(revision>0),updated_at INTEGER NOT NULL CHECK(updated_at>0),PRIMARY KEY(owner,slot))')
  db.execute('CREATE TABLE IF NOT EXISTS housing_preset_receipts(operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,request_hash TEXT NOT NULL,slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 3),created_at INTEGER NOT NULL CHECK(created_at>0))')
  db.execute('INSERT INTO '+TABLE+' VALUES(?,?,?,1,?,?,?) ON CONFLICT(owner,slot)DO UPDATE SET payload=excluded.payload,revision=excluded.revision,updated_at=excluded.updated_at',(owner,slot,account,encode(wire.PRESET,preset),revision,stamp))
  db.execute('INSERT INTO '+RECEIPTS+' VALUES(?,?,?,?,?,?)',(operation,owner,account,digest,slot,stamp))
  answer=[wire.acknowledgement(preset)]
  for event in answer:encode_event(event)
  guard(db)
  if not WRITES_ENABLED:raise ValueError('Housing preset writer changed before commit')
  return answer
