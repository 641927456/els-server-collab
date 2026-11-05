"""Owned Silver Mirror progression within the caller's real SQL transaction.

No constructor or install migration writes. Runtime callers must bind a current
session lease, exact source graph and server-issued run UUID before admission.
"""
import hashlib
import json
import math
import time
import uuid
import secrets

from els_server.domain import silver_mirror_policy as policy
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS silver_mirror_state (
        owner INTEGER PRIMARY KEY, week INTEGER NOT NULL, progress INTEGER NOT NULL,
        memory INTEGER NOT NULL, remaining INTEGER NOT NULL, buff0 INTEGER NOT NULL,
        buff1 INTEGER NOT NULL, revision INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS silver_mirror_runs (
        run_id TEXT PRIMARY KEY, owner INTEGER NOT NULL, account_id INTEGER NOT NULL,
        session_id TEXT NOT NULL, dungeon INTEGER NOT NULL, week INTEGER NOT NULL,
        source_sha256 TEXT NOT NULL, stage_slot INTEGER NOT NULL,
        proof_sha256 TEXT, result_json TEXT)''')
    db.execute('CREATE TABLE IF NOT EXISTS silver_mirror_seeds(run_id TEXT PRIMARY KEY,seed TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS silver_mirror_offers(run_id TEXT PRIMARY KEY,slot INTEGER NOT NULL,offers_json TEXT NOT NULL,chosen INTEGER NOT NULL,proof_sha256 TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS silver_mirror_buffs(owner INTEGER NOT NULL,slot INTEGER NOT NULL,week INTEGER NOT NULL,template INTEGER NOT NULL,starts_at INTEGER NOT NULL,run_id TEXT NOT NULL,PRIMARY KEY(owner,slot))')


def guard(db, owner, account_id, authorize):
    if not db.in_transaction or not callable(authorize) or authorize() is not True:
        raise ValueError('Silver Mirror requires current owned transaction authority')
    require_owner(db, owner, account_id)
    require_active_character(db, owner)


def clock(now):
    now = time.time() if now is None else now
    if type(now) not in (int, float) or not math.isfinite(now):
        raise ValueError('Silver Mirror finite server clock required')
    return now, policy.week_start(now)


def validate(state):
    if set(state) != {'owner', 'week', 'progress', 'memory', 'remaining', 'buff0', 'buff1', 'revision'}:
        raise ValueError('Silver Mirror stored state shape')
    if any(type(v) is not int for v in state.values()):
        raise ValueError('Silver Mirror stored integer state')
    policy.week_start(state['week'])
    if policy.week_start(state['week']) != state['week']:
        raise ValueError('Silver Mirror stored week identity')
    policy.validate_progress(state['progress'])
    if not 0 <= state['memory'] <= 4 or not 0 <= state['remaining'] <= 5:
        raise ValueError('Silver Mirror stored weekly counters')
    if any(not 0 <= state[k] < 2**31 for k in ('buff0', 'buff1', 'revision')):
        raise ValueError('Silver Mirror stored buff or revision range')
    return state


def read(db, owner, now=None):
    _, week = clock(now)
    row = None
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='silver_mirror_state'").fetchone():
        row = db.execute('SELECT owner,week,progress,memory,remaining,buff0,buff1,revision FROM silver_mirror_state WHERE owner=?', (owner,)).fetchone()
    old = validate(dict(zip(('owner', 'week', 'progress', 'memory', 'remaining', 'buff0', 'buff1', 'revision'), row))) if row else None
    if old and old['week'] > week:
        raise ValueError('Silver Mirror persisted future week')
    if old and old['week'] == week:
        return old
    return dict(owner=owner, week=week, progress=0, memory=0, remaining=5,
                buff0=0, buff1=0, revision=old['revision'] + 1 if old else 0)


def save(db, state):
    validate(state)
    db.execute('''INSERT INTO silver_mirror_state VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(owner) DO UPDATE SET week=excluded.week,progress=excluded.progress,
        memory=excluded.memory,remaining=excluded.remaining,buff0=excluded.buff0,
        buff1=excluded.buff1,revision=excluded.revision''', tuple(state[k] for k in ('owner', 'week', 'progress', 'memory', 'remaining', 'buff0', 'buff1', 'revision')))


def _uuid(value, version):
    if type(value) is not str or str(uuid.UUID(value)) != value or uuid.UUID(value).version != version:
        raise ValueError('Silver Mirror server identity')


def _sha(value):
    if type(value) is not str or len(value) != 64 or bytes.fromhex(value).hex() != value:
        raise ValueError('Silver Mirror source fingerprint')


def admit(db, owner, account_id, run_id, session_id, dungeon, source_sha256, authorize, *, now=None):
    guard(db, owner, account_id, authorize)
    _uuid(run_id, 4)
    _uuid(session_id, 4)
    _sha(source_sha256)
    # Clock is sampled only after the caller holds BEGIN IMMEDIATE.
    now, _ = clock(now)
    state = read(db, owner, now)
    index = policy.eligible(state['week'], state['memory'], state['progress'], dungeon)
    ensure(db)
    prior = db.execute('SELECT owner,account_id,session_id,dungeon,week,source_sha256,stage_slot,proof_sha256 FROM silver_mirror_runs WHERE run_id=?', (run_id,)).fetchone()
    identity = (owner, account_id, session_id, dungeon, state['week'], source_sha256, index)
    if prior:
        if prior[:7] != identity or prior[7] is not None:
            raise ValueError('Silver Mirror run UUID already belongs to another or completed run')
    else:
        db.execute('INSERT INTO silver_mirror_runs VALUES (?,?,?,?,?,?,?,?,NULL,NULL)', (run_id, *identity))
        seed=secrets.token_hex(32)
        db.execute('INSERT INTO silver_mirror_seeds VALUES (?,?)',(run_id,seed))
        if index in(0,1):
            from els_server.domain.silver_mirror_catalog import buff_pool
            pool=[b for b in buff_pool(dungeon)if b not in(state['buff0'],state['buff1'])]
            pool.sort(key=lambda b:hashlib.sha256((seed+':buff:'+str(b)).encode()).digest())
            if len(pool)<3:raise ValueError('Silver Mirror distinct offer pool')
            db.execute('INSERT INTO silver_mirror_offers VALUES (?,?,?,0,NULL)',(run_id,index,json.dumps(pool[:3])))
    save(db, state)
    guard(db, owner, account_id, authorize)
    return dict(state=state, slot=index)


def complete(db, owner, account_id, run_id, session_id, dungeon, source_sha256, proof, authorize, *, now=None):
    guard(db, owner, account_id, authorize)
    if not isinstance(proof, bytes) or not 1 <= len(proof) <= 65536:
        raise ValueError('Silver Mirror exact accepted clear proof required')
    _uuid(run_id, 4)
    _uuid(session_id, 4)
    _sha(source_sha256)
    row = db.execute('SELECT owner,account_id,session_id,dungeon,week,source_sha256,stage_slot,proof_sha256,result_json FROM silver_mirror_runs WHERE run_id=?', (run_id,)).fetchone()
    if not row or row[:4] != (owner, account_id, session_id, dungeon) or row[5] != source_sha256:
        raise ValueError('Silver Mirror clear was not admitted by this actor and source')
    digest = hashlib.sha256(proof).hexdigest()
    if row[7] is not None:
        if row[7] != digest:
            raise ValueError('Silver Mirror conflicting committed clear proof')
        return dict(result=json.loads(row[8]), replayed=True)
    now, week = clock(now)
    if row[4] != week:
        raise ValueError('Silver Mirror run crossed weekly deployment boundary')
    state = read(db, owner, now)
    change = policy.cleared(week, state['memory'], state['progress'], state['remaining'], dungeon)
    if change['slot']in(0,1):
        selected=db.execute('SELECT chosen,proof_sha256 FROM silver_mirror_offers WHERE run_id=?',(run_id,)).fetchone()
        if not selected or not selected[0]or not selected[1]or state['buff'+str(change['slot'])]!=selected[0]:raise ValueError('Silver Mirror native buff selection not completed')
    if change['slot'] != row[6]:
        raise ValueError('Silver Mirror original deployment stage changed')
    updated = dict(state, **{k: change[k] for k in ('progress', 'memory', 'remaining')}, revision=state['revision'] + 1)
    if change['clear_buffs']:
        updated.update(buff0=0, buff1=0)
        db.execute('DELETE FROM silver_mirror_buffs WHERE owner=?',(owner,))
    result = dict(before=state, after=updated, weekly=change['weekly'], slot=change['slot'], dungeon=dungeon)
    save(db, updated)
    db.execute('UPDATE silver_mirror_runs SET proof_sha256=?,result_json=? WHERE run_id=? AND proof_sha256 IS NULL', (digest, json.dumps(result, sort_keys=True, separators=(',', ':')), run_id))
    guard(db, owner, account_id, authorize)
    return dict(result=result, replayed=False)


def offers(db,run_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='silver_mirror_offers'").fetchone():return []
    row=db.execute('SELECT offers_json FROM silver_mirror_offers WHERE run_id=?',(run_id,)).fetchone()
    return json.loads(row[0])if row else []


def select(db,owner,account_id,run_id,session_id,dungeon,source_sha256,choice,proof,authorize,*,now=None):
    guard(db,owner,account_id,authorize)
    now,week=clock(now)
    row=db.execute('SELECT owner,account_id,session_id,dungeon,week,source_sha256,stage_slot,proof_sha256 FROM silver_mirror_runs WHERE run_id=?',(run_id,)).fetchone()
    if not row or row[:6]!=(owner,account_id,session_id,dungeon,week,source_sha256)or row[6]not in(0,1):raise ValueError('Silver Mirror choice source')
    offered=db.execute('SELECT slot,offers_json,chosen,proof_sha256 FROM silver_mirror_offers WHERE run_id=?',(run_id,)).fetchone()
    if not offered or type(choice)is not int or choice not in json.loads(offered[1])or not isinstance(proof,bytes)or not proof:raise ValueError('Silver Mirror choice was not offered')
    digest=hashlib.sha256(proof).hexdigest()
    state=read(db,owner,now)
    if offered[2]:
        if(offered[2],offered[3])!=(choice,digest):raise ValueError('Silver Mirror choice conflicts with committed source')
        return state
    if row[7]is not None:raise ValueError('Silver Mirror choice after clear')
    index=policy.eligible(week,state['memory'],state['progress'],dungeon)
    if index!=offered[0]:raise ValueError('Silver Mirror choice deployment changed')
    state=dict(state,**{'buff'+str(index):choice},revision=state['revision']+1)
    save(db,state)
    db.execute('UPDATE silver_mirror_offers SET chosen=?,proof_sha256=? WHERE run_id=? AND chosen=0',(choice,digest,run_id))
    db.execute('INSERT INTO silver_mirror_buffs VALUES (?,?,?,?,?,?) ON CONFLICT(owner,slot)DO UPDATE SET week=excluded.week,template=excluded.template,starts_at=excluded.starts_at,run_id=excluded.run_id',(owner,index,week,choice,int(now),run_id))
    guard(db,owner,account_id,authorize)
    return state


def world_rows(db,owner,*,now=None):
    now,week=clock(now);state=read(db,owner,now)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='silver_mirror_buffs'").fetchone():
        if state['buff0']or state['buff1']:raise ValueError('Silver Mirror buff source missing')
        return []
    rows=[]
    for slot,stored_week,template,start,run_id in db.execute('SELECT slot,week,template,starts_at,run_id FROM silver_mirror_buffs WHERE owner=? ORDER BY slot',(owner,)):
        if stored_week!=week:continue
        if slot not in(0,1)or state['buff'+str(slot)]!=template:raise ValueError('Silver Mirror buff ownership state')
        proof=db.execute('SELECT r.owner,r.week,o.chosen,o.proof_sha256 FROM silver_mirror_runs r JOIN silver_mirror_offers o ON o.run_id=r.run_id WHERE r.run_id=?',(run_id,)).fetchone()
        if not proof or proof[:3]!=(owner,week,template)or not proof[3]:raise ValueError('Silver Mirror buff accepted source missing')
        rows.append(dict(owner=owner,template=template,start=start,end=week+7*86400,_silver=True))
    if {r['template']for r in rows}!={b for b in(state['buff0'],state['buff1'])if b}:raise ValueError('Silver Mirror incomplete world snapshot')
    return rows


def seed(db,run_id):
    row=db.execute('SELECT seed FROM silver_mirror_seeds WHERE run_id=?',(run_id,)).fetchone()
    if not row or len(row[0])!=64:raise ValueError('Silver Mirror original draw seed missing')
    return row[0]
