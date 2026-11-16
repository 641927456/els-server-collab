"""Ordinary accepted-death misc draws and atomic, source-bound ground pickup."""
import hashlib,json,sqlite3,time,uuid
from contextlib import closing
from pathlib import Path
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'))
def key(c):return tuple(c[k]for k in('owner','run_id','stage','part','visits','npc_key'))
def ensure(db):
 if not db.in_transaction:raise ValueError('Ordinary misc requires caller writer')
 db.execute('''CREATE TABLE IF NOT EXISTS ordinary_misc_loot_issues(
 owner INTEGER NOT NULL REFERENCES characters(uid),run_id TEXT NOT NULL,stage INTEGER NOT NULL,
 part INTEGER NOT NULL,visits INTEGER NOT NULL,npc_key INTEGER NOT NULL,
 context_json TEXT NOT NULL,origin_json TEXT NOT NULL,proof_sha256 TEXT NOT NULL,rows_json TEXT NOT NULL,
 PRIMARY KEY(owner,run_id,stage,part,visits,npc_key))''')
def lookup(db,c):
 return db.execute('SELECT context_json,origin_json,proof_sha256,rows_json FROM ordinary_misc_loot_issues WHERE owner=?AND run_id=?AND stage=?AND part=?AND visits=?AND npc_key=?',key(c)).fetchone()

def issue(db,source,proof,start_id,xyz,randbelow):
 from els_server.domain.ordinary_misc_loot import ATMA_TEMPLE,POLICY,plans,temple_rewards
 if not isinstance(proof,bytes)or not proof or len(proof)>8192:raise ValueError('Ordinary misc death proof')
 c=source.c;source.validate(db);ensure(db);digest=hashlib.sha256(proof).hexdigest();old=lookup(db,c)
 if old is not None:
  if old[:3]!=(canonical(c),canonical(source.origin),digest):raise ValueError('Conflicting ordinary misc death')
  return json.loads(old[3])
 from els_server.storage.elixir_economy import bonus
 temple=c['dungeon']==ATMA_TEMPLE
 drop_bp=0 if temple else bonus(db,c['owner'],c['dungeon'],'drop','elixir-misc:'+str(uuid.uuid5(uuid.UUID(c['run_id']),canonical(c))),dict(c,policy=POLICY,proof_sha256=digest))
 rewards=plans(source,randbelow,drop_bp)
 if temple and source.origin.get('reward_actor') is not None:
  from els_server.storage.atma_temple_weekly import spend
  if spend(db,c['owner'],int(time.time())):rewards.extend(temple_rewards(source,randbelow))
 rows=[]
 for offset,(template,quantity)in enumerate(rewards):
  drop_id=start_id+offset
  if type(drop_id)is not int or not 1<=drop_id<2**31:raise ValueError('Ordinary misc drop identity bound')
  rows.append(dict(c,template=template,quantity=quantity,drop_id=drop_id,xyz=list(xyz),ed=0,source=POLICY,pickup_committed=False,claimed_uids=None,death_proof_sha256=digest,misc_origin=source.origin))
 db.execute('INSERT INTO ordinary_misc_loot_issues VALUES(?,?,?,?,?,?,?,?,?,?)',(*key(c),canonical(c),canonical(source.origin),digest,canonical(rows)))
 return rows
def claim(path,c,drop,request,account,prepare,validate):
 from els_server.domain.ordinary_misc_loot import POLICY,catalog
 from els_server.domain.reward_rules import item_plan
 from els_server.domain.raid_reward_items import _issue_source
 if request['drop_id']!=drop['drop_id']or request['template']!=drop['template']:raise ValueError('Ordinary misc requested issue')
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db:
  db.execute('PRAGMA foreign_keys=ON')
  with write_transaction(db):
   validate(db);old=lookup(db,c)
   if old is None or old[:3]!=(canonical(c),canonical(drop['misc_origin']),drop['death_proof_sha256']):raise ValueError('Ordinary misc committed source missing')
   rows=json.loads(old[3]);row=next((r for r in rows if r['drop_id']==request['drop_id']),None)
   if(row is None or row['source']!=POLICY or row['template']!=request['template']or row['quantity']!=drop['quantity'] or row['template']not in map(int,catalog()['items'])or any(row.get(k)!=v for k,v in c.items())):raise ValueError('Ordinary misc exact issued item')
   operation='ordinary-misc-pickup:'+str(uuid.uuid5(uuid.UUID(c['run_id']),canonical(dict(c,drop_id=row['drop_id']))))
   owner,digest=_identity(c['owner'],0xd0,canonical(dict(c,drop_id=row['drop_id'],source=POLICY,proof=old[2])).encode(),operation)
   before=load_items(db,owner);prior=_previous(db,operation,digest)
   if prior is not None:
    if row['claimed_uids']is None:raise ValueError('Ordinary misc receipt/source mismatch')
    ids=set(row['claimed_uids']);replies=prepare([i for i in before if i['uid']in ids],True);validate(db)
    return dict(reply=replies,replayed=True)
   if row['claimed_uids']is not None:raise ValueError('Ordinary misc issue has no pickup receipt')
   plan=[item_plan(row['template'],row['quantity'])]
   def guard(writer):
    if writer is not db or lookup(writer,c)!=old:raise ValueError('Ordinary misc source changed before factory')
    return validate(writer)
   cap=_issue_source(db,owner,operation,'ordinary',dict(reward_source=POLICY,context=c,origin=row['misc_origin'],drop_id=row['drop_id'],proof_sha256=old[2]),plan,guard)
   awarded=grant_items(db,plan,owner,raid_reward_source=cap,dungeon_drop=True);after=load_items(db,owner);ids={i['uid']for i in awarded};current=[i for i in after if i['uid']in ids]
   replies=prepare(current,False);validate(db)
   _commit(db,operation,digest,owner,0xd0,[(i['group'],i['slot'])for i in current],before,after)
   row['claimed_uids']=sorted(ids);row['pickup_committed']=True
   db.execute('UPDATE ordinary_misc_loot_issues SET rows_json=?WHERE owner=?AND run_id=?AND stage=?AND part=?AND visits=?AND npc_key=?',(canonical(rows),*key(c)))
   return dict(reply=replies,replayed=False)

from els_server.storage.sqlite_timing import write_transaction
