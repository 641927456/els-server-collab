"""Owned30day712417 and repeatable7day189800 on the native character-wide slot.

Never credits the permanent invested map or its available point budget. The
native renderer/ability lookup clamps selected permanent+5 to the original max.
"""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import json,sqlite3,time
from els_server.domain.resonance_2026_allocations import ResonanceRejected
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.protocol.resonance_period_messages import request,reply,notice
from els_server.protocol.protocol_codec import encode_event

TEMPLATE=712417
POINTS=5
PERIOD=720*3600
ITEM_SHA='72714343697b75f7a44fdd5ee5cb67acefa1e0120ed3627bcb6def71597bb721'
TABLE='character_resonance_period'
MENTOR_TEMPLATE=189800
MENTOR_TABLE='character_mentor_resonance_period'
MENTOR_PERIOD=7*86400
SQL='CREATE TABLE character_resonance_period (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),stat_id INTEGER NOT NULL CHECK(stat_id>0),points INTEGER NOT NULL CHECK(points=5),expires_at INTEGER NOT NULL CHECK(expires_at>0),updated_at INTEGER NOT NULL CHECK(updated_at>0),source_uid INTEGER NOT NULL CHECK(source_uid>0))'
WRITES_ENABLED=True
MENTOR_SQL=SQL.replace(TABLE,MENTOR_TABLE)

def snapshot(db,account,character,*,mentor=False):
 from els_server.storage.profession_state import require_owner
 require_owner(db,character,account)
 table=MENTOR_TABLE if mentor else TABLE;sql=MENTOR_SQL if mentor else SQL
 schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table'AND name=?",(table,)).fetchone()
 if schema is None:return None
 if schema!=(sql,):raise ValueError('Unknown resonance period schema')
 row=db.execute('SELECT account_id,stat_id,points,expires_at,updated_at,source_uid FROM '+table+' WHERE owner=?',(character,)).fetchone()
 if row is None:return None
 if (row[0]!=account or any(type(v)is not int or v<=0 for v in row[1:])or row[2]!=POINTS
     or not(MENTOR_PERIOD<=row[3]-row[4]<=PERIOD if mentor else row[3]-row[4]==PERIOD)):
  raise ValueError('Saved resonance period identity')
 from els_server.domain.resonance_allocation_flow import definitions
 from els_server.domain.resonance_2026_allocations import ResonanceAllocations
 ResonanceAllocations.from_original(definitions()[1]).stat(row[1])
 return row[1:]

def active(db,account,character,*,now=None):
 stamp=time.time()if now is None else now
 if type(stamp)not in(int,float)or stamp<=0:raise ValueError('Resonance period authority clock')
 rows=[row for row in(snapshot(db,account,character),snapshot(db,account,character,mentor=True))if row is not None and row[2]>stamp]
 if len(rows)>1:raise ValueError('Conflicting native character-wide blessings')
 return rows[0]if rows else None

def key(db,account,character):
 rows=(snapshot(db,account,character),snapshot(db,account,character,mentor=True))
 return tuple(None if row is None else(*row,row[2]>time.time())for row in rows)

def project(db,account,character,state):
 opaque=(state.field21,state.field25,state.field29,state.field31,state.field32)
 # Preserve imported unsupported metadata; this consumer cannot reinterpret it.
 if opaque!=(0,0,0,0,0):return state
 row=active(db,account,character)
 if row is None:return state
 return replace(state,field21=row[0],field25=row[1],field29=row[2],field31=state.selected_page)

def bonus(state):
 return ((state.field21,state.field25),)if state.field21 and state.field25 else()

def use(path,character,account,payload,operation,guard,*,now=None):
 source,stat,page=request(payload);character,digest=_identity(character,0x718,b'owned712417:'+payload,operation)
 if not callable(guard):raise ValueError('Resonance period current actor guard')
 from els_server.domain.resonance_allocation_flow import profiles
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.resonance_state import snapshot as legacy
 def authority(db):
  guard(db);require_active_character(db,character)
  original=legacy(db,character,account)
  if not original['enabled']:raise ResonanceRejected(1788,'Resonance period requires opened ERP')
  return original
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');original=authority(db)
  before=load_items(db,character);old=_previous(db,operation,digest)
  item=next((i for i in before if i['uid']==source),None)
  if old is None and(item is None or item['template']not in(TEMPLATE,MENTOR_TEMPLATE)):raise ResonanceRejected(459,'Owned current blessing source required')
  p=profiles(db);p.initialize();p.accounts.migrate_dominated_legacy(account=account,character=character)
  state=p.synchronize(account=account,character=character);pages=p.pages.read(account,character);metadata=p._metadata(account,character)
  if not pages.enabled or metadata[1]!=(0,0,0,0,0):raise ValueError('Unverified imported period state')
  p.pages.rules.stat(stat)
  if old is not None:
   proof=json.loads(db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()[0])
   source_row=next((i for i in proof if i['uid']==source),None)
   if (source_row is None or source_row['template']not in(TEMPLATE,MENTOR_TEMPLATE)
       or snapshot(db,account,character,mentor=source_row['template']==MENTOR_TEMPLATE)is None):raise ValueError('Resonance period receipt proof')
   answer=[reply(tuple(current_changes(db,operation,character,0x718,old,before))),state.notice()]
   for event in answer:encode_event(event)
   authority(db);return answer
  if not WRITES_ENABLED:raise ValueError('Resonance period writer held')
  stamp=int(time.time())if now is None else now
  if type(stamp)is not int or stamp<=0:raise ValueError('Resonance period use clock')
  if page!=pages.selected_page:raise ResonanceRejected(2051,'Stale resonance period selected page')
  mentor=item['template']==MENTOR_TEMPLATE
  current=active(db,account,character,now=stamp)
  if current is not None:
   if not mentor or snapshot(db,account,character,mentor=True)!=current or current[0]!=stat:
    raise ValueError('Native character-wide blessing already active on another source/stat')
  end=min((stamp if current is None else current[2])+(MENTOR_PERIOD if mentor else PERIOD),stamp+PERIOD)
  if current is not None and end<=current[2]:raise ValueError('Blessing already at30day limit; no debit')
  if item['metadata']!=0 or item['group']!=4 or not 1<=item['count']<2**31:raise ValueError('Blessing source shape')
  from els_server.domain.item_expiration import require_current
  from els_server.domain.item_locks import require_unlocked
  require_current(item,now=stamp);require_unlocked(item,now=stamp)
  if item.get('sealed',False):raise ValueError('Sealed blessing source')
  table=MENTOR_TABLE if mentor else TABLE;sql=MENTOR_SQL if mentor else SQL
  if not db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():db.execute(sql)
  saved=(stat,POINTS,end,stamp,source)
  db.execute('INSERT INTO '+table+' VALUES(?,?,?,?,?,?,?)ON CONFLICT(owner)DO UPDATE SET stat_id=excluded.stat_id,points=excluded.points,expires_at=excluded.expires_at,updated_at=excluded.updated_at,source_uid=excluded.source_uid',(character,account,*saved))
  if item['count']==1:remove(db,character,item)
  elif db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=?AND uid=?AND count=?',(character,source,item['count'])).rowcount!=1:raise ValueError('Blessing source changed')
  after=load_items(db,character);position=(item['group'],item['slot']);current=next((i for i in after if i['uid']==source),None)
  state=p.synchronize(account=account,character=character);answer=[reply(((position,current),)),notice(state)]
  for event in answer:encode_event(event)
  if authority(db)!=original or not WRITES_ENABLED or snapshot(db,account,character,mentor=mentor)!=saved or p.pages.read(account,character)!=pages or load_items(db,character)!=after:raise ValueError('Blessing late authority changed')
  _commit(db,operation,digest,character,0x718,[position],before,after);return answer
