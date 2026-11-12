"""Lazy mission ledger; all awards share the original clear SQL transaction."""
import hashlib,json,secrets,time,uuid
from els_server.domain import random_mission_rules as rules
from els_server.storage.normal_fatigue import _writer,_actor

RUN_SQL='CREATE TABLE random_mission_runs(reward_run TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),context_json TEXT NOT NULL,context_sha256 TEXT NOT NULL,found INTEGER NOT NULL CHECK(found IN(0,1)),mission INTEGER NOT NULL,percent INTEGER NOT NULL,buff INTEGER NOT NULL,level INTEGER NOT NULL,started_at INTEGER NOT NULL,completed INTEGER NOT NULL CHECK(completed IN(0,1)),clear_sha256 TEXT NOT NULL,bonus_experience INTEGER NOT NULL CHECK(bonus_experience>=0))'
EFFECT_SQL='CREATE TABLE random_mission_effects(owner INTEGER NOT NULL REFERENCES characters(uid),buff INTEGER NOT NULL,stacks INTEGER NOT NULL CHECK(stacks BETWEEN 1 AND 3),starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,reward_run TEXT NOT NULL REFERENCES random_mission_runs(reward_run),clear_sha256 TEXT NOT NULL,PRIMARY KEY(owner,buff))'
QUICK_SQL='''CREATE TABLE IF NOT EXISTS random_mission_quick_uses(
    reward_run TEXT PRIMARY KEY REFERENCES random_mission_runs(reward_run),
    target INTEGER NOT NULL CHECK(target BETWEEN 2 AND 5),
    used INTEGER NOT NULL CHECK(used BETWEEN 0 AND target),
    completed_by TEXT UNIQUE,
    CHECK((used=target)=(completed_by IS NOT NULL)))'''
QUICK_EFFECT_SQL='''CREATE TABLE IF NOT EXISTS random_mission_quick_effects(
    owner INTEGER NOT NULL REFERENCES characters(uid), buff INTEGER NOT NULL,
    stacks INTEGER NOT NULL CHECK(stacks BETWEEN 1 AND 3),
    starts_at INTEGER NOT NULL, ends_at INTEGER NOT NULL,
    reward_run TEXT NOT NULL REFERENCES random_mission_quick_uses(reward_run), PRIMARY KEY(owner,buff))'''
COLUMNS=('reward_run','owner','context_json','context_sha256','found','mission','percent','buff','level','started_at','completed','clear_sha256','bonus_experience')

def _exists(db,name):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(name,)).fetchone())
def _clock(now=None):
    now=int(time.time())if now is None else now
    if type(now)is not int or not 1<=now<2**31-7200:raise ValueError('Mission epoch')
    return now

def _context(c):
    keys={'owner','account','reward_run','epoch','dungeon','graph_sha256','stage','part','visits','roster','policy'}
    if type(c)is not dict or set(c)!=keys or c['policy']!=rules.policy()['identity']or c['visits']!=2 or any(type(c[k])is not int for k in('owner','account','dungeon','stage','part','visits'))or not 1001<=c['owner']<2**63 or not 0<c['account']<2**63 or not 0<=c['stage']<2**31 or not 0<=c['part']<128:raise ValueError('Mission source context')
    uuid.UUID(c['reward_run']);uuid.UUID(c['epoch']);r=rules.route(c['dungeon'])
    if r is None or r['graph_sha256']!=c['graph_sha256']or not isinstance(c['roster'],list)or not 1<=len(c['roster'])<=4 or c['roster']!=sorted(set(c['roster']))or c['owner']not in c['roster']:raise ValueError('Mission finite source/roster')
    raw=json.dumps(c,sort_keys=True,separators=(',',':'));return raw,hashlib.sha256(raw.encode()).hexdigest()

def saved(db,reward_run,owner):
    if not _exists(db,'random_mission_runs'):return None
    row=db.execute('SELECT * FROM random_mission_runs WHERE reward_run=?',(reward_run,)).fetchone()
    if row is None:return None
    d=dict(zip(COLUMNS,row));c=json.loads(d['context_json']);raw,digest=_context(c)
    if d['owner']!=owner or c['owner']!=owner or d['reward_run']!=c['reward_run']or(raw,digest)!=(d['context_json'],d['context_sha256'])or d['found']not in(0,1)or d['completed']not in(0,1)or not 1<=d['level']<=99 or not 1<=d['started_at']<2**31 or not 0<=d['bonus_experience']<2**63:raise ValueError('Mission saved identity')
    if d['found']:
        if not 0<d['mission']<2**31 or d['percent']not in(110,120,150,200,300,500)or d['buff']not in rules.pool(d['level']):raise ValueError('Mission saved reward')
    elif(d['mission'],d['percent'],d['buff'],d['completed'],d['clear_sha256'],d['bonus_experience'])!=(0,0,0,0,'',0):raise ValueError('Mission saved no-hit')
    if d['completed']:
        if len(d['clear_sha256'])!=64:raise ValueError('Mission committed proof')
        bytes.fromhex(d['clear_sha256'])
    elif(d['clear_sha256'],d['bonus_experience'])!=('',0):raise ValueError('Mission premature reward')
    d['quick']=quick_progress(db,reward_run)
    if d['quick'] is not None and (not d['found'] or d['completed'] and not d['quick'][2]):
        raise ValueError('Mission saved quick-slot completion')
    return d

def quick_progress(db,reward_run):
    if not _exists(db,'random_mission_quick_uses'):return None
    return db.execute('SELECT target,used,completed_by FROM random_mission_quick_uses WHERE reward_run=?',
                      (reward_run,)).fetchone()

def quick_complete(db,row):
    if not row['quick'] or not row['quick'][2]:return False
    receipt=db.execute('SELECT owner FROM consumable_uses WHERE operation_id=?',(row['quick'][2],)).fetchone()
    if receipt!=(row['owner'],):raise ValueError('Mission quick-slot receipt owner')
    return True

def stage(db,path,contexts,prepare,*,now=None,entry_rate=0):
    _writer(db,path);prepare(db);now=_clock(now)
    if not rules.enabled():return[]
    if not 1<=len(contexts)<=4:raise ValueError('Mission source cohort')
    sources=[_context(c)for c in contexts];owners={c['owner']for c in contexts};common={json.dumps({k:v for k,v in c.items()if k not in('owner','account','reward_run')},sort_keys=True)for c in contexts}
    if len(owners)!=len(contexts)or len(common)!=1 or any(set(c['roster'])!=owners for c in contexts):raise ValueError('Mission original shared cohort')
    for c in contexts:_actor(db,c['owner'],c['account'])
    previous=[saved(db,c['reward_run'],c['owner'])for c in contexts]
    if any(previous):
        if not all(previous)or any((d['context_json'],d['context_sha256'])!=source for d,source in zip(previous,sources)):raise ValueError('Mission partial or conflicting replay')
        prepare(db);return previous
    # A live holder's original finite inventory receipt proves the100% effect.
    from els_server.storage.world_elixirs import _state
    guaranteed=any(any(r['template']==110004681 for r in _state(db,c['owner'],now)['rows'])for c in contexts)
    policy=rules.policy()
    chance=policy['potion_chance'] if guaranteed else policy['base_chance']+entry_rate
    found=int(secrets.randbelow(100)<chance);percent=mission=0
    if found:
        mission=secrets.randbelow(2**31-1)+1;draw=secrets.randbelow(100)
        for value,weight in policy['experience_weights']:
            draw-=weight
            if draw<0:percent=value;break
    # Share a uniform reward rank within the party. Twelve is divisible by
    # both original pool sizes, so each level pool remains exactly uniform.
    reward_rank=secrets.randbelow(12)if found else 0
    # Four equally likely clear outcomes and one for each approved quick-slot target.
    mission_draw=secrets.randbelow(8) if found else 0
    target=mission_draw-2 if mission_draw>=4 else 0
    db.execute(RUN_SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1));out=[]
    if target:db.execute(QUICK_SQL)
    for c,(raw,digest)in zip(contexts,sources):
        level=db.execute('SELECT level FROM characters WHERE uid=?',(c['owner'],)).fetchone()[0];pool=rules.pool(level);buff=pool[reward_rank*len(pool)//12]if found else 0
        row=(c['reward_run'],c['owner'],raw,digest,found,mission,percent,buff,level,now,0,'',0);db.execute('INSERT INTO random_mission_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',row);out.append(dict(zip(COLUMNS,row)))
        out[-1]['quick']=(target,0,None) if target else None
        if target:db.execute('INSERT INTO random_mission_quick_uses VALUES(?,?,0,NULL)',(c['reward_run'],target))
    prepare(db);return out

def consume_quick_slot(db,path,owner,account,reward_run,operation,now):
    _writer(db,path);_actor(db,owner,account)
    row=saved(db,reward_run,owner)
    if row is None or row['quick'] is None or row['completed']:return False
    target,used,completed_by=row['quick']
    if completed_by:return False
    used+=1
    completed=used==target
    db.execute('UPDATE random_mission_quick_uses SET used=?,completed_by=? WHERE reward_run=?',
               (used,operation if completed else None,reward_run))
    if not completed:return False
    row['quick']=(target,used,operation)
    quick_complete(db,row)
    stacks=_next_stacks(db,row,now)
    db.execute(QUICK_EFFECT_SQL)
    db.execute('''INSERT INTO random_mission_quick_effects VALUES(?,?,?,?,?,?)
        ON CONFLICT(owner,buff) DO UPDATE SET stacks=excluded.stacks,starts_at=excluded.starts_at,
        ends_at=excluded.ends_at,reward_run=excluded.reward_run''',
        (owner,row['buff'],stacks,now,now+1800,reward_run))
    return True

def complete(db,path,owner,account,reward_run,proof,base_experience,validate):
    _writer(db,path);_actor(db,owner,account);validate(db);row=saved(db,reward_run,owner)
    if not rules.enabled()or row is None or row['found']!=1:raise ValueError('Mission original selected clear required')
    if type(base_experience)is not int or not 0<=base_experience<2**63 or not isinstance(proof,bytes):raise ValueError('Mission original clear value')
    digest=hashlib.sha256(proof).hexdigest()
    if row['completed']:
        if row['clear_sha256']!=digest:raise ValueError('Mission clear proof changed')
        return row
    # Native text30705 says an additional clear-EXP percentage. The original
    # GM-pinned clear base is used once; title bonuses and the later ERP10x
    # remain in their existing independent paths.
    bonus=base_experience*row['percent']//100
    if bonus>=2**63:raise ValueError('Mission clear amount overflow')
    db.execute('UPDATE random_mission_runs SET completed=1,clear_sha256=?,bonus_experience=? WHERE reward_run=?AND owner=?AND completed=0',(digest,bonus,reward_run,owner));validate(db);return saved(db,reward_run,owner)

def apply_effect(db,path,row,validate,*,now=None):
    _writer(db,path);validate(db);now=_clock(now);current=saved(db,row['reward_run'],row['owner'])
    if current!=row or row['completed']!=1:raise ValueError('Mission completed source required')
    receipt=db.execute('SELECT proof_sha256 FROM reward_receipts WHERE run_id=?',(row['reward_run'],)).fetchone()
    if receipt!=(row['clear_sha256'],):raise ValueError('Mission original clear receipt required')
    stacks=_next_stacks(db,row,now)
    db.execute(EFFECT_SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1));old=db.execute('SELECT stacks,ends_at,reward_run FROM random_mission_effects WHERE owner=?AND buff=?',(row['owner'],row['buff'])).fetchone()
    if old and old[2]==row['reward_run']:return
    db.execute('INSERT INTO random_mission_effects VALUES(?,?,?,?,?,?,?)ON CONFLICT(owner,buff)DO UPDATE SET stacks=excluded.stacks,starts_at=excluded.starts_at,ends_at=excluded.ends_at,reward_run=excluded.reward_run,clear_sha256=excluded.clear_sha256',(row['owner'],row['buff'],stacks,now,now+1800,row['reward_run'],row['clear_sha256']));validate(db)
    if _exists(db,'random_mission_quick_effects'):
        db.execute('DELETE FROM random_mission_quick_effects WHERE owner=? AND buff=?',(row['owner'],row['buff']))

def _next_stacks(db,row,now):
    active=next((r for r in effects(db,row['owner'],now=now) if r['template']==row['buff']),None)
    return min(3,active['stacks']+1) if active else 1

def effects(db,owner,*,now=None):
    now=_clock(now)
    out={}
    for table,proof in (('random_mission_effects','clear_sha256'),('random_mission_quick_effects','NULL')):
        if not _exists(db,table):continue
        rows=db.execute(f'SELECT buff,stacks,starts_at,ends_at,reward_run,{proof} FROM {table} WHERE owner=?',(owner,))
        for buff,stacks,start,end,run,digest in rows:
            rules.effect(buff);source=saved(db,run,owner)
            if source is None or source['buff']!=buff or not 1<=stacks<=3 or not 1<=start<end<2**31 or end-start!=1800:
                raise ValueError('Mission saved effect identity')
            if proof=='NULL':
                if not quick_complete(db,source):raise ValueError('Mission saved quick-slot effect source')
            elif (not source['completed'] or source['clear_sha256']!=digest
                  or db.execute('SELECT proof_sha256 FROM reward_receipts WHERE run_id=?',(run,)).fetchone()!=(digest,)):
                raise ValueError('Mission saved clear effect source')
            if rules.enabled() and now<end:
                out[buff]=dict(_mission=True,owner=owner,template=buff,stacks=stacks,start=start,end=end)
    return [out[buff] for buff in sorted(out)]
