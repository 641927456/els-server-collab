"""Per-issued-actor character EXP receipts in the accepted-death transaction."""
import hashlib,json,uuid
from pathlib import Path

FIELDS=('owner','run_id','dungeon','stage','part','visits','npc_key','template','graph_sha256',
        'policy','policy_sha256','npc_level','base_experience','table_experience','experience_bp')

def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS pve_kill_experience (
      owner INTEGER NOT NULL,run_id TEXT NOT NULL,stage INTEGER NOT NULL,part INTEGER NOT NULL,
      visits INTEGER NOT NULL,npc_key INTEGER NOT NULL,identity_json TEXT NOT NULL,
      proof_sha256 TEXT NOT NULL,experience INTEGER NOT NULL CHECK(experience>=0),operation_id TEXT NOT NULL UNIQUE,
      PRIMARY KEY(owner,run_id,stage,part,visits,npc_key))''')

def commit(db,store,c,proof,killer,*,require_existing=False):
    from els_server.domain.dungeon_lifecycle import experience_death_notice
    from els_server.domain.legacy_pve_exp import experience_limit
    if not db.in_transaction or set(c)!=set(FIELDS) or store.uid!=c['owner']:raise ValueError('Kill EXP transaction/context')
    actual=db.execute('PRAGMA database_list').fetchone()[2]
    if Path(actual).resolve()!=Path(store.path).resolve():raise ValueError('Kill EXP transaction database/ownership')
    from els_server.storage import resonance_state as er
    er.owner(db,c['owner'],getattr(store,'account_id',None))
    if any(type(c[k]) is not int or c[k]<0 for k in ('owner','dungeon','stage','part','npc_key','template','base_experience')) or type(c['visits']) is not int or c['visits']<1:raise ValueError('Kill EXP identity bound')
    if c['owner']<1001 or c['dungeon']==0 or type(c['npc_level']) is not int or not 1<=c['npc_level']<=100 or not 0<=c['base_experience']<=2**31-1:raise ValueError('Kill EXP source bound')
    if (type(c['table_experience']) is not int or not 1<=c['table_experience']<=2**31-1
        or type(c['experience_bp']) is not int or not 0<=c['experience_bp']<=1000000
        or c['base_experience']!=min(2**31-1,c['table_experience']*c['experience_bp']//10000)):
        raise ValueError('Kill EXP pinned multiplier/source')
    if any(len(bytes.fromhex(c[k]))!=32 for k in ('graph_sha256','policy_sha256')):raise ValueError('Kill EXP source digest')
    if not isinstance(proof,bytes) or not proof or len(proof)>8192:raise ValueError('Kill EXP proof')
    run=uuid.UUID(c['run_id']);canonical=json.dumps(c,sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256(proof).hexdigest();key=tuple(c[k] for k in ('owner','run_id','stage','part','visits','npc_key'))
    ensure(db)
    prior=db.execute('SELECT identity_json,proof_sha256,experience,operation_id FROM pve_kill_experience WHERE owner=? AND run_id=? AND stage=? AND part=? AND visits=? AND npc_key=?',key).fetchone()
    if prior:
        if prior[:2]!=(canonical,digest):raise ValueError('Conflicting accepted kill EXP')
        if not db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(prior[3],)).fetchone():raise ValueError('Missing committed kill reward receipt')
        award=er.receipt(db,prior[3])
        if award is not None and (award['account_id']!=er.owner(db,c['owner'],getattr(store,'account_id',None)) or award['owner']!=c['owner']):raise ValueError('ERP kill receipt account changed')
        return dict(experience=prior[2],replayed=True)
    if require_existing:raise ValueError('Loot replay missing matching kill EXP receipt')
    character=db.execute('SELECT level FROM characters WHERE uid=?',(c['owner'],)).fetchone()
    if character is None:raise ValueError('Kill EXP character missing')
    total=db.execute('SELECT experience FROM reward_balances WHERE uid=?',(c['owner'],)).fetchone()
    if total is None:raise ValueError('Kill EXP balance missing')
    mode=er.route(db,c['owner'],getattr(store,'account_id',None))
    amount=c['base_experience'] if mode=='resonance' else (0 if character[0]>=99 else min(c['base_experience'],max(0,experience_limit()-total[0])))
    operation=str(uuid.uuid5(run,':'.join(map(str,('ordinary-kill-exp-v1',*key)))))
    evidence=b'ordinary-kill-exp-v1\0'+canonical.encode()+b'\0'+bytes.fromhex(digest)
    def encode(balances):
        award=er.receipt(db,operation)
        effective=award['effective'] if award is not None else balances['experience']-total[0]
        return experience_death_notice(c['npc_key'],killer,c['owner'],effective).payload
    result=store.grant(operation,evidence,0,amount,encode,
                transaction=db,experience_limit=experience_limit(),resonance_source='kill')
    amount=result['resonance_award']['effective'] if 'resonance_award' in result else result['balances']['experience']-total[0]
    db.execute('INSERT INTO pve_kill_experience VALUES (?,?,?,?,?,?,?,?,?,?)',(*key,canonical,digest,amount,operation))
    return dict(experience=amount,replayed=False)

def run_total(db,owner,run_id,*,clear_basis=False):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pve_kill_experience'").fetchone():return 0
    if clear_basis:
        from els_server.storage import resonance_state as er
        rows=db.execute('SELECT experience,operation_id FROM pve_kill_experience WHERE owner=? AND run_id=?',(owner,run_id)).fetchall()
        total=0
        for effective,operation in rows:
            award=er.receipt(db,operation)
            if award is None:
                total+=effective;continue
            saved=db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(operation,)).fetchone()
            if saved is None:raise ValueError('Missing kill reward multiplier receipt')
            plan=json.loads(saved[0]);multiplier=plan.get('resonance_multiplier',1)
            if type(multiplier) is not int or multiplier not in (1,10) or award['source']!='kill' or award['owner']!=owner or award['effective']!=effective or award['requested']!=plan['experience']*multiplier:raise ValueError('Invalid kill reward multiplier receipt')
            # Only the pre-ERP-multiplier amount feeds the 30% clear base.
            # Historical 1x and new 10x receipts may coexist in a saved run.
            total+=effective//multiplier
        return total
    return db.execute('SELECT COALESCE(SUM(experience),0) FROM pve_kill_experience WHERE owner=? AND run_id=?',(owner,run_id)).fetchone()[0]
