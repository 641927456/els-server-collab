"""Original housing expansion items: consume, persist and acknowledge atomically."""
from contextlib import closing
from pathlib import Path
import json,sqlite3,time
from els_server.domain.housing_expansion_rules import STEP_ITEMS,FLOOR_ITEMS,PRESET_ITEMS
from els_server.protocol import housing_expansion_messages as wire
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import housing_rooms,housing_access
from els_server.storage.item_actor import require_active_character
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes

WRITES_ENABLED=True
TABLE='character_housing_options_v1'
TEMPLATES=frozenset(STEP_ITEMS+FLOOR_ITEMS+PRESET_ITEMS)

def preset_expansions(db,owner,account):
 housing_access.owner(db,owner,account)
 if not housing_rooms.exists(db,TABLE):return 0
 row=db.execute('SELECT account_id,extra_presets FROM '+TABLE+' WHERE owner=?',(owner,)).fetchone()
 if row is None:return 0
 if row[0]!=account or type(row[1])is not int or not 0<=row[1]<=3:raise ValueError('Unknown saved housing preset allowance')
 return row[1]

def require_room(db,owner,account,generation,admission,stamp):
 require_active_character(db,owner);housing_access.owner(db,owner,account)
 if not housing_access.active(housing_access.snapshot(db,owner,account),stamp):raise ValueError('Current housing access required')
 row=db.execute('SELECT owner,account_id,generation FROM housing_room_admissions WHERE operation_id=?',(admission,)).fetchone()
 room=housing_rooms.snapshot(db,owner,account)
 if row!=(owner,account,generation)or room is None or room['generation']!=generation:raise ValueError('Housing durable admission changed')
 if db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()!=(99,):raise ValueError('Housing owner level99 required')
 return room

def write_floors(db,owner,account,floors):
 db.execute('UPDATE character_housing_rooms_v1 SET layout_json=? WHERE owner=? AND account_id=?',
            (json.dumps(sorted(floors.items()),separators=(',',':')),owner,account))
 housing_rooms.snapshot(db,owner,account)

def notifications(db,owner,account,template,target,floors):
 answer=[wire.info(floors,preset_expansions(db,owner,account))]
 if template in STEP_ITEMS:
  from els_server.storage.housing_layouts import snapshot
  saved=snapshot(db,owner,account,floor=target)
  answer.append(wire.stage(floors[target][0],[]if saved is None else saved['layout'][2],target,floors[target][1]))
 return answer

def use(path,owner,account,payload,operation,generation,admission,guard,*,now=None):
 source,target=wire.use_request(payload);owner,digest=_identity(owner,0x219,b'HousingExpansion:'+payload,operation)
 if not callable(guard):raise ValueError('Housing expansion current actor')
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard(db)
  stamp=int(time.time())if now is None else now
  if type(stamp)is not int or not 0<stamp<2**63:raise ValueError('Housing expansion time')
  room=require_room(db,owner,account,generation,admission,stamp);floors=dict(room['layout'])
  before=load_items(db,owner);old=_previous(db,operation,digest)
  item=next((i for i in before if i['uid']==source),None)
  balance=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()
  if balance is None or type(balance[0])is not int or not 0<=balance[0]<2**63:raise ValueError('Housing ED integrity')
  if old is not None:
   historic=db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=? AND owner=? AND kind=537',(operation,owner)).fetchone()
   item=next((i for i in json.loads(historic[0])if i['uid']==source),None)if historic is not None else None
   if item is None or item['template']not in TEMPLATES:raise ValueError('Housing expansion receipt source')
   answer=[use_ack(current_changes(db,operation,owner,0x219,old,before),item['template'],balance[0])]+notifications(db,owner,account,item['template'],target,floors)
   for e in answer:encode_event(e)
   guard(db);return answer
  if not WRITES_ENABLED:raise ValueError('Housing expansion writer held')
  if item is None or item['template']not in TEMPLATES or(item['metadata'],item['group'],item['count'])!=(0,4,1):raise ValueError('Owned housing expansion contract required')
  from els_server.domain.item_expiration import require_current
  from els_server.domain.item_locks import require_unlocked
  require_current(item,now=stamp);require_unlocked(item,now=stamp)
  if item.get('sealed',False)or item.get('seal_count',0):raise ValueError('Housing contract is sealed')
  template=item['template']
  if template in STEP_ITEMS:
   if target not in floors or floors[target][0]>=4 or STEP_ITEMS[floors[target][0]]!=template:raise ValueError('Next housing stage contract and owned floor required')
   new=floors[target][0]+1;floors[target]=(new,new);write_floors(db,owner,account,floors)
  elif template in FLOOR_ITEMS:
   if len(floors)>=3 or target!=len(floors)+1:raise ValueError('Next housing floor required')
   floors[len(floors)]=(0,0);write_floors(db,owner,account,floors)
  else:
   count=preset_expansions(db,owner,account)
   if target or count>=3:raise ValueError('Housing preset allowance reached')
   db.execute('CREATE TABLE IF NOT EXISTS character_housing_options_v1 (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL,extra_presets INTEGER NOT NULL CHECK(extra_presets BETWEEN 0 AND 3))')
   db.execute('INSERT INTO '+TABLE+' VALUES (?,?,?) ON CONFLICT(owner)DO UPDATE SET extra_presets=excluded.extra_presets',(owner,account,count+1))
  from els_server.storage.item_instances import remove
  remove(db,owner,item);after=load_items(db,owner);positions=[(item['group'],item['slot'])]
  from els_server.storage.housing_achievements import update as achievements
  answer=[use_ack([(positions[0],None)],template,balance[0])]+notifications(db,owner,account,template,target,floors)+achievements(db,owner,account,stamp)
  for e in answer:encode_event(e)
  _commit(db,operation,digest,owner,0x219,positions,before,after)
  guard(db)
  if not WRITES_ENABLED:raise ValueError('Housing expansion held before commit')
  return answer
