"""Lazy mission ledger; all awards share the original clear SQL transaction."""
import hashlib,json,secrets,time,uuid
from els_server.domain import random_mission_rules as rules
from els_server.storage.normal_fatigue import _writer,_actor

RUN_SQL='CREATE TABLE random_mission_runs(reward_run TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),context_json TEXT NOT NULL,context_sha256 TEXT NOT NULL,found INTEGER NOT NULL CHECK(found IN(0,1)),mission INTEGER NOT NULL,percent INTEGER NOT NULL,buff INTEGER NOT NULL,level INTEGER NOT NULL,started_at INTEGER NOT NULL,completed INTEGER NOT NULL CHECK(completed IN(0,1)),clear_sha256 TEXT NOT NULL,bonus_experience INTEGER NOT NULL CHECK(bonus_experience>=0))'
EFFECT_SQL='CREATE TABLE random_mission_effects(owner INTEGER NOT NULL REFERENCES characters(uid),buff INTEGER NOT NULL,stacks INTEGER NOT NULL CHECK(stacks BETWEEN 1 AND 3),starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,reward_run TEXT NOT NULL REFERENCES random_mission_runs(reward_run),clear_sha256 TEXT NOT NULL,PRIMARY KEY(owner,buff))'
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
    return d

def stage(db,path,contexts,prepare,*,now=None):
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
    found=int(secrets.randbelow(100)<(100 if guaranteed else 20));percent=mission=0
    if found:
        mission=secrets.randbelow(2**31-1)+1;draw=secrets.randbelow(100)
        for value,weight in rules.policy()['experience_weights']:
            draw-=weight
            if draw<0:percent=value;break
    # Share a uniform reward rank within the party. Twelve is divisible by
    # both original pool sizes, so each level pool remains exactly uniform.
    reward_rank=secrets.randbelow(12)if found else 0
    db.execute(RUN_SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1));out=[]
    for c,(raw,digest)in zip(contexts,sources):
        level=db.execute('SELECT level FROM characters WHERE uid=?',(c['owner'],)).fetchone()[0];pool=rules.pool(level);buff=pool[reward_rank*len(pool)//12]if found else 0
        row=(c['reward_run'],c['owner'],raw,digest,found,mission,percent,buff,level,now,0,'',0);db.execute('INSERT INTO random_mission_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',row);out.append(dict(zip(COLUMNS,row)))
    prepare(db);return out

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
    effects(db,row['owner'],now=now)
    db.execute(EFFECT_SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1));old=db.execute('SELECT stacks,ends_at,reward_run FROM random_mission_effects WHERE owner=?AND buff=?',(row['owner'],row['buff'])).fetchone()
    if old and old[2]==row['reward_run']:return
    stacks=min(3,old[0]+1)if old and now<old[1]else 1
    db.execute('INSERT INTO random_mission_effects VALUES(?,?,?,?,?,?,?)ON CONFLICT(owner,buff)DO UPDATE SET stacks=excluded.stacks,starts_at=excluded.starts_at,ends_at=excluded.ends_at,reward_run=excluded.reward_run,clear_sha256=excluded.clear_sha256',(row['owner'],row['buff'],stacks,now,now+1800,row['reward_run'],row['clear_sha256']));validate(db)

def effects(db,owner,*,now=None):
    now=_clock(now)
    if not _exists(db,'random_mission_effects'):return[]
    rows=db.execute('SELECT buff,stacks,starts_at,ends_at,reward_run,clear_sha256 FROM random_mission_effects WHERE owner=?ORDER BY buff',(owner,)).fetchall();out=[]
    if len(rows)>10:raise ValueError('Mission finite native effect pool')
    for buff,stacks,start,end,run,digest in rows:
        rules.effect(buff);source=saved(db,run,owner)
        if source is None or not source['completed']or(source['buff'],source['clear_sha256'])!=(buff,digest)or not 1<=stacks<=3 or not 1<=start<end<2**31 or end-start!=1800 or db.execute('SELECT proof_sha256 FROM reward_receipts WHERE run_id=?',(run,)).fetchone()!=(digest,):raise ValueError('Mission saved effect source')
        if rules.enabled()and now<end:out.append(dict(_mission=True,owner=owner,template=buff,stacks=stacks,start=start,end=end))
    return out
