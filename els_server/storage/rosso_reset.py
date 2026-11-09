"""One SQL debit/reset/receipt; historical raid runs never become new grants."""
from contextlib import closing
import json,sqlite3,struct,time,uuid
from els_server.domain.rosso_reset import TEMPLATE,definition,request
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.npc_trade import balances
from els_server.storage import raid_economy_state as state
from els_server.protocol.career_messages import use_ack
from els_server.protocol.raid_economy_protocol import weekly_snapshot
from els_server.protocol.protocol_codec import encode_event

def recognizes(path,owner,payload,operation):
 if type(payload)is not bytes or len(payload)<8:return False
 item_uid=struct.unpack_from('>Q',payload)[0]
 if not 0<item_uid<2**63:return False
 with closing(sqlite3.connect(path,timeout=10))as db:
  row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(owner,item_uid)).fetchone()
  if row==(TEMPLATE,):return True
  return bool(state.exists(db,'inventory_action_receipts')and db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=? AND owner=? AND kind=?',(operation,owner,0x219)).fetchone())

def _events(db,owner,now,changes,template=0):
 # Existing7C1 schema: category1 and third/sixth i32 are normal/story steps.
 wallet=balances(db,owner);week=state.week_at(now)
 out=[use_ack(changes,template,wallet['ed']),weekly_snapshot(1,state.weekly_steps(db,owner,'rosso',week),state.weekly_steps(db,owner,'rosso',week,True))]
 for event in out:encode_event(event)
 return out

def perform(path,owner,account,payload,operation,*,prepare):
 item_uid,bucket=request(payload);owner,digest=_identity(owner,0x219,payload,operation)
 if not operation.startswith('rosso-reset-v1:')or not callable(prepare):raise ValueError('Rosso reset exact operation/authority')
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.profession_state import require_owner
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 from els_server.storage.item_instances import remove
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  require_active_character(db,owner);require_owner(db,owner,account)
  if prepare(db)is not True:raise ValueError('Rosso current writer required')
  now=int(time.time());week=state.week_at(now);definition()
  old=_previous(db,operation,digest);items=load_items(db,owner)
  if old is not None:
   saved=db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=? AND owner=? AND kind=?',(operation,owner,0x219)).fetchone()
   before=json.loads(saved[0])if saved else[]
   if len(before)!=1 or before[0]['uid']!=item_uid or before[0]['template']!=TEMPLATE:raise ValueError('Rosso original ticket receipt changed')
   # Never clear newly earned eligibility when an old reset is replayed.
   events=_events(db,owner,now,current_changes(db,operation,owner,0x219,old,items))
   if prepare(db)is not True:raise ValueError('Rosso replay lease expired')
   return events
  from els_server.domain.rosso_reset import ADMISSIONS_ENABLED
  if not ADMISSIONS_ENABLED:raise ValueError('New Rosso ticket use closed')
  item=next((i for i in items if i['uid']==item_uid),None)
  if item is None or(item['template'],item['metadata'],item['group'])!=(TEMPLATE,0,4):raise ValueError('Exact original owned Rosso ticket required')
  require_current(item,now=now);require_unlocked(item,now=now)
  if item.get('sealed',False)or item.get('seal_used',0):raise ValueError('Rosso ticket seal state')
  if not state.exists(db,'formal_raid_weeks'):raise ValueError('Rosso has no real current-week reward information')
  if db.execute('SELECT 1 FROM formal_raid_weeks WHERE owner=? AND week>? LIMIT 1',(owner,week)).fetchone():raise ValueError('Future raid week requires independent review')
  rows=db.execute('SELECT ordinal,phase,run FROM formal_raid_weeks WHERE owner=? AND bucket=? AND week=? ORDER BY ordinal,phase',(owner,bucket,week)).fetchall()
  if not rows:raise ValueError('Selected Rosso mode already has no claimed weekly reward')
  for ordinal,phase,run in rows:
   if type(ordinal)is not int or type(phase)is not int or ordinal not in(1,2,3)or phase not in(1,2,3)or str(uuid.UUID(run))!=run:raise ValueError('Unknown persisted Rosso weekly phase')
  wallet=balances(db,owner)
  if wallet['revision']>=2**63-1:raise ValueError('Rosso ticket balance revision overflow')
  position=(item['group'],item['slot'])
  if item['count']==1:remove(db,owner,item)
  else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,owner))
  deleted=db.execute('DELETE FROM formal_raid_weeks WHERE owner=? AND bucket=? AND week=?',(owner,bucket,week)).rowcount
  if deleted!=len(rows):raise ValueError('Rosso selected weekly ledger changed')
  # Historical formal_raid_phases, reward_receipts and other weeks/modes/families
  # are immutable. Only a fresh original run may fill these now-empty slots.
  after=load_items(db,owner);current=next((i for i in after if i['uid']==item_uid),None)
  events=_events(db,owner,now,[(position,current)],TEMPLATE)
  db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
  _commit(db,operation,digest,owner,0x219,[position],[dict(item)],[]if current is None else[dict(current)])
  if prepare(db)is not True:raise ValueError('Rosso ticket lease changed after encoding')
  return events
