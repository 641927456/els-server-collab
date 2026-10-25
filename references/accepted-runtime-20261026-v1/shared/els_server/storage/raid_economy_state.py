"""Weekly, repeat and pity are one original phase writer; reads create no schema."""
import hashlib,json,uuid
from datetime import datetime,timedelta,timezone
from els_server.domain import formal_raid_economy as rules

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))

def ensure(db):
 if not db.in_transaction:raise ValueError('Raid ledger requires original writer')
 db.execute('''CREATE TABLE IF NOT EXISTS formal_raid_phases (
 owner INTEGER NOT NULL,run TEXT NOT NULL,stage INTEGER NOT NULL,dungeon INTEGER NOT NULL,
 week INTEGER NOT NULL,proof TEXT NOT NULL,source TEXT NOT NULL,result TEXT NOT NULL,
 PRIMARY KEY(owner,run,stage))''')
 db.execute('''CREATE TABLE IF NOT EXISTS formal_raid_weeks (
 owner INTEGER NOT NULL,bucket TEXT NOT NULL,ordinal INTEGER NOT NULL,phase INTEGER NOT NULL,
 week INTEGER NOT NULL,run TEXT NOT NULL,PRIMARY KEY(owner,bucket,ordinal,phase,week))''')
 db.execute('''CREATE TABLE IF NOT EXISTS formal_raid_progress (
 owner INTEGER NOT NULL,kind TEXT NOT NULL,points INTEGER NOT NULL CHECK(points>=0),
 generation INTEGER NOT NULL CHECK(generation>=0),PRIMARY KEY(owner,kind))''')

def exists(db,table):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

def week_at(now):
 if type(now)is not int or not 1600000000<=now<2**31:raise ValueError('Raid server clock bound')
 d=datetime.fromtimestamp(now,timezone(timedelta(hours=8)));day=d.replace(hour=10,minute=0,second=0,microsecond=0)
 start=day-timedelta(days=(day.weekday()-2)%7)
 if d<start:start-=timedelta(days=7)
 return int(start.timestamp())

def progress(db,owner,kind):
 if not exists(db,'formal_raid_progress'):return 0,0
 row=db.execute('SELECT points,generation FROM formal_raid_progress WHERE owner=? AND kind=?',(owner,kind)).fetchone()
 if row is None:return 0,0
 if any(type(v)is not int or not 0<=v<2**31 for v in row):raise ValueError('Raid persisted progress bound')
 maximum=100 if kind.startswith('accessory:')else rules.maximum(kind)
 if row[0]>maximum:raise ValueError('Raid persisted progress exceeds current original threshold')
 return row

def set_progress(db,owner,kind,points,generation=None):
 old,gen=progress(db,owner,kind)
 if generation is None:generation=gen
 limit=100 if kind.startswith('accessory:')else rules.maximum(kind)
 if type(points)is not int or not 0<=points<=limit or type(generation)is not int or not 0<=generation<2**31:raise ValueError('Raid new progress bound')
 db.execute('INSERT INTO formal_raid_progress VALUES (?,?,?,?) ON CONFLICT(owner,kind) DO UPDATE SET points=excluded.points,generation=excluded.generation',(owner,kind,points,generation))

def weekly(db,owner,d,stage,week):
 if not exists(db,'formal_raid_weeks'):return False
 return bool(db.execute('SELECT 1 FROM formal_raid_weeks WHERE owner=? AND bucket=? AND ordinal=? AND phase=? AND week=?',(owner,d['week_bucket'],d['ordinal'],d['phases'][str(stage)],week)).fetchone())

def weekly_steps(db,owner,family,week,story=False):
 """Known native clear-step projection of this server's committed week ledger.

 No schema is installed by a login/read. Unknown historic progress is not
 migrated. A branch can advance only after all earlier native phases exist.
 """
 if not exists(db,'formal_raid_weeks'):return 0
 bucket=family+(':story'if story else ':shared')
 rows=set(db.execute('SELECT ordinal,phase FROM formal_raid_weeks WHERE owner=? AND bucket=? AND week=?',(owner,bucket,week)))
 if family=='abyss':
  # Mineral/Crib is a branch choice, not permission to combine half of each.
  branch=max((2,3),key=lambda n:sum(all((n,p)in rows for p in range(1,end+1))for end in(1,2)))
  rows={r for r in rows if r[0]not in(2,3)or r[0]==branch}
 if family=='rosso':nodes=[[(n,p)]for n in range(1,4)for p in range(1,4)];ends={2:10,5:20,8:30}
 elif family=='berthe':nodes=[[(n,p)]for n in range(1,3)for p in range(1,4)];ends={2:10,5:20}
 elif family=='abyss':nodes=[[(1,1)],[(1,2)],[(2,1),(3,1)],[(2,2),(3,2)],[(4,1)],[(4,2)],[(4,3)]];ends={1:10,3:20,6:30}
 elif family=='conductor':nodes=[[(n,p)]for n in range(1,3)for p in range(1,3)];ends={1:10,3:20}
 elif family=='barkat':nodes=[[(n,p)]for n in range(1,5)for p in range(1,3)]+[[(5,3)]];ends={1:10,3:20,5:30,7:40,8:50}
 elif family=='marcus':nodes=[[(n,p)]for n,count in enumerate((2,2,2,2,1),1)for p in range(1,count+1)];ends={1:10,3:20,5:30,7:40,8:50}
 else:raise ValueError('Raid current progress category')
 value=0
 for i,choices in enumerate(nodes):
  if not any(x in rows for x in choices):break
  value=ends.get(i,value+1)
 return value

def prepare_batch(db,contexts,now,guard):
 """Context is built only by the original loaded native phase consumer.

 The runtime guard is checked before and after SQL and again after all response
 encoding by the caller. It binds concrete sessions, original runs and roster.
 """
 if not db.in_transaction or guard(db)is not True:raise ValueError('Raid original phase authority')
 if not isinstance(contexts,list)or not 1<=len(contexts)<=6:raise ValueError('Raid original roster size')
 owners=[r['owner']for r in contexts]
 if len(set(owners))!=len(owners):raise ValueError('Raid duplicate roster owner')
 generations={(r['source_run'],r['dungeon'],r['stage'],r['part'],r['visits'],r['graph_sha256'])for r in contexts}
 if len(generations)!=1:raise ValueError('Raid peer source generation differs')
 ensure(db);week=week_at(now);prepared=[];fresh=[]
 for c in contexts:
  if type(c['owner'])is not int or c['owner']<1001 or type(c['alive'])is not bool:raise ValueError('Raid original actor/life type')
  if str(uuid.UUID(c['run']))!=c['run']or str(uuid.UUID(c['source_run']))!=c['source_run']:raise ValueError('Raid run UUID')
  d=rules.definition(c['dungeon'])
  if d is None or d['graph_sha256']!=c['graph_sha256']or str(c['stage'])not in d['phases']:raise ValueError('Raid current finite source')
  if type(c['proof'])is not str or len(bytes.fromhex(c['proof']))!=32:raise ValueError('Raid phase source proof')
  source={**c,'policy_sha256':rules.policy()['_sha256'],'roster':owners}
  old=db.execute('SELECT dungeon,proof,source,result FROM formal_raid_phases WHERE owner=? AND run=? AND stage=?',(c['owner'],c['run'],c['stage'])).fetchone()
  if old is not None:
   if old[:3]!=(c['dungeon'],c['proof'],canonical(source)):raise ValueError('Conflicting raid phase replay')
   saved=json.loads(old[3]);saved['replayed']=True;prepared.append(saved);continue
  if db.execute('SELECT 1 FROM formal_raid_weeks WHERE owner=? AND week>? LIMIT 1',(c['owner'],week)).fetchone():raise ValueError('Raid future weekly ledger')
  first=not weekly(db,c['owner'],d,c['stage'],week)
  if d['family']=='marcus'and d['mode']=='story':first=False
  value=dict(owner=c['owner'],run=c['run'],source=source,week=week,first=first,replayed=False)
  prepared.append(value);fresh.append((c,d,value))
 # First-clear status is sampled for the entire original roster before any
 # member consumes a weekly slot. Later members cannot affect earlier rewards.
 if fresh and len(fresh)!=len(contexts):raise ValueError('Raid atomic roster has partial historical settlement')
 first_owners={r['owner']for r in prepared if r['first']}
 for c,d,result in fresh:
  owner=c['owner'];f=d['family'];first=result['first'];last=c['stage']==max(map(int,d['phases']))
  if first:db.execute('INSERT INTO formal_raid_weeks VALUES (?,?,?,?,?,?)',(owner,d['week_bucket'],d['ordinal'],d['phases'][str(c['stage'])],week,c['run']))
  points=progress(db,owner,f)[0]if f in('rosso','berthe','abyss','barkat')else 0
  if first and f in('rosso','berthe','abyss'):
   suffix='story'if d['mode']=='story'else 'normal';points=min(rules.maximum(f),points+rules.policy()['local'][f+'_points_'+suffix])
  rows,new_points=rules.pools(d,c['stage'],first,c['source_run'],owner,points)
  if f in('rosso','berthe','abyss','barkat'):
   _,gen=progress(db,owner,f);set_progress(db,owner,f,new_points,gen+int(new_points<points))
  subtype={'conductor':1,'barkat':2,'marcus':3}.get(f)
  if subtype is not None and first and(f!='marcus'or last):
   key='accessory:'+str(subtype);p,g=progress(db,owner,key);set_progress(db,owner,key,min(100,p+rules.policy()['local']['accessory_gain_percent'][str(subtype)]),g)
  if f=='barkat'and first and last and d['ordinal']in rules.policy()['official']['barkat_heart_maps']:
   # Hearts are for a real full map, not merely joining its last native phase.
   previous=db.execute('SELECT stage FROM formal_raid_phases WHERE owner=? AND run=? AND dungeon=?',(owner,c['run'],c['dungeon'])).fetchall()
   if set(s for(s,)in previous)|{c['stage']}==set(map(int,d['phases'])):rows.append((136181,3))
  if f=='marcus'and d['mode']=='normal'and not first and c['alive']:
   unit=rules.policy()['official']['marcus_marks'][d['ordinal']-1][c['stage']]
   count=len(first_owners-{owner})*unit
   if count:rows.append((119317,count))
  if f in('rosso','berthe','abyss')and d['mode']in('normal','solo')and not first and c['alive']:
   count=len(first_owners-{owner})*rules.policy()['local']['old_raid_repeat_mark_unit']
   if count:rows.append((rules.policy()['local']['old_raid_repeat_marks'][f],count))
  result.update(items=rules.plan(rows),weapon_winner=any(t in(135902,136054,136106,136180)for t,n in rows),points=new_points,
   phase_experience=c['phase_experience'],replayed=False)
 # The original Rosso/Berthe crystal rule awards at most one to each other
 # eligible original participant, including repeat receivers, even when
 # multiple weapon boxes drop.
 winners={r['owner']for r in prepared if r.get('weapon_winner')}
 for c,d,result in fresh:
  if winners and d['family']in('rosso','berthe')and c['owner']not in winners:
   rows=[(r['template'],r['quantity'])for r in result['items']];rows.append((135910 if d['family']=='rosso'else 136057,1));result['items']=rules.plan(rows)
  db.execute('INSERT INTO formal_raid_phases VALUES (?,?,?,?,?,?,?,?)',(c['owner'],c['run'],c['stage'],c['dungeon'],week,c['proof'],canonical(result['source']),canonical(result)))
 if guard(db)is not True:raise ValueError('Raid original phase changed before encoding')
 return prepared

def run_experience(db,owner,run,dungeon):
 rows=db.execute('SELECT stage,result FROM formal_raid_phases WHERE owner=? AND run=? AND dungeon=?',(owner,run,dungeon)).fetchall()
 d=rules.definition(dungeon)
 if d is None or {s for s,r in rows}!=set(map(int,d['phases'])):raise ValueError('Raid full native phase EXP ledger incomplete')
 return min(2**31-1,sum(json.loads(r)['phase_experience']for s,r in rows))
