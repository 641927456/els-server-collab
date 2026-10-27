"""Lazy source ledger + per-character week counter, one real writer per action.

No existing table alteration, eager DDL, read migration or shadow transaction.
Ground items remain server-owned issues until ordinary native pickup commits.
"""
from contextlib import closing,contextmanager
import json,secrets,sqlite3,hashlib,uuid,time
from els_server.domain.hunter_chest_rules import POLICY,advance,reward,week,digest
from els_server.protocol.profession_messages import ProfessionState
from els_server.storage.profession_state import snapshot,replace,require_owner
from els_server.storage.item_actor import require_active_character
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))

@contextmanager
def writer(path,authorize):
 with closing(sqlite3.connect(path,timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
  authorize(db);yield db;authorize(db)

def ensure(db):
 db.execute('''CREATE TABLE IF NOT EXISTS hunter_chest_sources (
   run_id TEXT PRIMARY KEY,context_json TEXT NOT NULL,source_json TEXT,
   death_sha256 TEXT,rewards_json TEXT,policy_id TEXT NOT NULL)''')
 db.execute('''CREATE TABLE IF NOT EXISTS hunter_chest_weeks (
   owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
   week INTEGER NOT NULL,count INTEGER NOT NULL CHECK(count BETWEEN 0 AND 500),
   PRIMARY KEY(owner,week))''')

def exists(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hunter_chest_sources'").fetchone())

def actors(db,context):
 result={}
 for row in context['roster']:
  uid,account=row['owner'],row['account']
  require_active_character(db,uid);require_owner(db,uid,account)
  state=snapshot(db,uid,account);result[uid]=state
  current=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()
  if current is None or current[0]<40:result[uid]=None
 return result

def generate(path,context,source,prepare,authorize,*,randbelow=secrets.randbelow):
 with writer(path,authorize)as db:
  states=actors(db,context)
  hunters=[uid for uid,s in states.items()if s is not None and s['state']['profession']==1 and 1<=s['state']['level']<=10]
  if not hunters:return None
  if exists(db):
   old=db.execute('SELECT context_json,source_json,policy_id FROM hunter_chest_sources WHERE run_id=?',(context['run_id'],)).fetchone()
   if old is not None:
    # A prior attempt in another part is terminal for this run, never rerolled.
    if old[2]!=POLICY:raise ValueError('Hunter source policy changed')
    if old[0]!=canonical(context):return None
    return prepare(json.loads(old[1])if old[1]else None,True)
  ensure(db)
  draw=randbelow(100)
  if type(draw)is not int or not 0<=draw<100:raise ValueError('Hunter spawn RNG')
  selected={**source,'eligible':hunters,'context_sha256':digest(context)}if draw<25 else None
  result=prepare(selected,False)
  db.execute('INSERT INTO hunter_chest_sources VALUES (?,?,?,NULL,NULL,?)',(context['run_id'],canonical(context),canonical(selected)if selected else None,POLICY))
  return result

def checked_source(db,context,source):
 if not exists(db):raise ValueError('Hunter source never generated')
 row=db.execute('SELECT context_json,source_json,death_sha256,rewards_json,policy_id FROM hunter_chest_sources WHERE run_id=?',(context['run_id'],)).fetchone()
 if row is None or row[0]!=canonical(context)or row[1]!=canonical(source)or row[4]!=POLICY:raise ValueError('Hunter saved source mismatch')
 return row

def destroy(path,context,source,proof,plans,prepare,authorize,*,now,randbelow=secrets.randbelow):
 if type(proof)is not bytes or not 1<=len(proof)<=8192:raise ValueError('Hunter death proof')
 proof_sha=hashlib.sha256(proof).hexdigest()
 with writer(path,authorize)as db:
  states=actors(db,context);row=checked_source(db,context,source)
  if row[2]is not None:
   if row[2]!=proof_sha:raise ValueError('Hunter conflicting death')
   return dict(replayed=True)
  # One clock sample only after BEGIN IMMEDIATE and its actor authorization.
  # Existing death receipts above never reinterpret their week or draw again.
  results={};week_id=week(now()if callable(now)else time.time()if now is None else now)
  for actor in context['roster']:
   uid=actor['owner'];saved=states[uid]
   if uid not in source['eligible']or saved is None or saved['state']['profession']!=1:continue
   latest=db.execute('SELECT MAX(week) FROM hunter_chest_weeks WHERE owner=?',(uid,)).fetchone()[0]
   if latest is not None and latest>week_id:raise ValueError('Hunter clock moved before saved week')
   before=ProfessionState(**saved['state'])
   if not 1<=before.level<=10:continue
   used=db.execute('SELECT count FROM hunter_chest_weeks WHERE owner=? AND week=?',(uid,week_id)).fetchone()
   if used is not None and used[0]>=500:continue
   roll=randbelow(100);item=reward(source['template'],roll);after,xp=advance(before,source['template'])
   if xp:replace(db,uid,actor['account'],saved['revision'],after)
   db.execute('INSERT INTO hunter_chest_weeks VALUES (?,?,1) ON CONFLICT(owner,week) DO UPDATE SET count=count+1',(uid,week_id))
   drop={**plans[uid],**item,'owner':uid,'source':POLICY,'source_run':context['run_id'],'context_sha256':digest(context),'death_sha256':proof_sha,'claimed_uids':None,'pickup_committed':False}
   results[uid]=dict(drop=drop,xp=xp,before=saved['state'],after=after)
  answer=prepare(results)
  ledger={str(uid):{**value,'after':value['after'].__dict__}for uid,value in results.items()}
  db.execute('UPDATE hunter_chest_sources SET death_sha256=?,rewards_json=? WHERE run_id=? AND death_sha256 IS NULL',(proof_sha,canonical(ledger),context['run_id']))
  return dict(replayed=False,prepared=answer)

def claim(path,context,source,owner,request,prepare,authorize):
 with writer(path,authorize)as db:
  actors(db,context);row=checked_source(db,context,source)
  if row[2]is None or row[3]is None:raise ValueError('Hunter box was not destroyed')
  saved=json.loads(row[3]);entry=saved.get(str(owner));drop=entry['drop']if entry else None
  if (drop is None or drop['drop_id']!=request['drop_id']or drop['template']!=request['template']or drop['owner']!=owner
      or drop['context_sha256']!=digest(context)or drop['death_sha256']!=row[2]):raise ValueError('Hunter owned issue mismatch')
  operation='hunter-chest-pickup:'+str(uuid.uuid5(uuid.UUID(context['run_id']),f"{owner}:{drop['drop_id']}"))
  _,request_hash=_identity(owner,0xd0,canonical(dict(context=context,drop_id=drop['drop_id'],death=row[2])).encode(),operation)
  prior=_previous(db,operation,request_hash);before=load_items(db,owner)
  if prior is not None:
   if drop['claimed_uids']is None:raise ValueError('Hunter pickup receipt mismatch')
   return dict(replayed=True)
  if drop['claimed_uids']is not None:raise ValueError('Hunter issue lost its receipt')
  awarded=grant_items(db,[{k:drop[k]for k in ('template','metadata','group','quantity')}],owner)
  after=load_items(db,owner);ids={i['uid']for i in awarded};current=[i for i in after if i['uid']in ids]
  result=prepare(current)
  _commit(db,operation,request_hash,owner,0xd0,[(i['group'],i['slot'])for i in current],before,after)
  drop['claimed_uids']=sorted(ids);drop['pickup_committed']=True
  db.execute('UPDATE hunter_chest_sources SET rewards_json=? WHERE run_id=?',(canonical(saved),context['run_id']))
  return dict(replayed=False,prepared=result)
