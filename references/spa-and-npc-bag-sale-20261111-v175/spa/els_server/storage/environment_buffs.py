"""Earned spa and Gate of Darkness deadlines, in the original source writer."""
import json,time

FESTIVAL_BUFF = 3456
FESTIVAL_TABLE = 'festival_buff_deadlines'
MAGMNA_TABLE = 'magmna_buff_deadlines'
TEMPLATES = {'gate':(202,), 'spa':(964,965)}
MAGMNA_TEMPLATES = (3083,3084)
REST_GROUPS = {
    964: TEMPLATES['spa'], 965: TEMPLATES['spa'],
    3083: MAGMNA_TEMPLATES, 3084: MAGMNA_TEMPLATES,
    FESTIVAL_BUFF: (FESTIVAL_BUFF,),
}

def exists(db,table='environment_buff_sources'):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def put(db,owner,source,operation,now):
    if not db.in_transaction:raise ValueError('Environment buff requires source transaction')
    if source in ('festival','magmna'):
        # Separate deadlines keep the existing environment_buff_sources
        # readable by older servers during a code-only recovery.
        table=FESTIVAL_TABLE if source=='festival' else MAGMNA_TABLE
        db.execute(f'''CREATE TABLE IF NOT EXISTS {table}(
            owner INTEGER PRIMARY KEY REFERENCES characters(uid), starts_at INTEGER NOT NULL,
            ends_at INTEGER NOT NULL, operation_id TEXT NOT NULL)''')
        db.execute(f'''INSERT INTO {table} VALUES(?,?,?,?)
            ON CONFLICT(owner)DO UPDATE SET starts_at=excluded.starts_at,
            ends_at=excluded.ends_at,operation_id=excluded.operation_id''',(owner,now,now+1800,operation))
        if source=='magmna' and exists(db):
            db.execute("DELETE FROM environment_buff_sources WHERE owner=? AND source='spa'",(owner,))
        return
    db.execute('''CREATE TABLE IF NOT EXISTS environment_buff_sources(
        owner INTEGER NOT NULL REFERENCES characters(uid),source TEXT NOT NULL,
        starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,operation_id TEXT NOT NULL,
        PRIMARY KEY(owner,source))''')
    db.execute('''INSERT INTO environment_buff_sources VALUES(?,?,?,?,?)
        ON CONFLICT(owner,source)DO UPDATE SET starts_at=excluded.starts_at,
        ends_at=excluded.ends_at,operation_id=excluded.operation_id''',
        (owner,source,now,now+1800,operation))
    if source=='spa':
        if exists(db,MAGMNA_TABLE):
            db.execute(f'DELETE FROM {MAGMNA_TABLE} WHERE owner=?',(owner,))
        from els_server.storage import achievements as achievements
        account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()[0]
        achievements._actor(db,account,owner);achievements.ensure(db)
        identity='spa-buff:'+operation
        digest,old=achievements._operation(db,account,owner,'spa-buff',dict(template=964,source=operation),identity)
        if old is None:achievements._save(db,account,owner,'spa-buff',digest,identity,dict(template=964,created_at=now))

def gate_clear(db,owner,run_id):
    # RewardState calls this only for a new committed38300 full-clear receipt.
    row=db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(run_id,)).fetchone()
    if row is None or json.loads(row[0]).get('dungeon_clear',[0])[0]!=38300:
        raise ValueError('Gate buff requires the original clear receipt')
    put(db,owner,'gate',run_id,int(time.time()))

def rows(db,owner,now,*,rest_only=False):
    result=_deadline_rows(db,owner,now,FESTIVAL_TABLE,(FESTIVAL_BUFF,))
    result+=_deadline_rows(db,owner,now,MAGMNA_TABLE,MAGMNA_TEMPLATES)
    if not exists(db):return result
    query='SELECT source,starts_at,ends_at,operation_id FROM environment_buff_sources WHERE owner=?'
    if rest_only:query+=" AND source='spa'"
    for source,start,end,operation in db.execute(query,(owner,)):
        if source not in TEMPLATES or not 1<=start<end<2**31 or end-start!=1800:
            raise ValueError('Environment buff save')
        if source=='gate':
            row=db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(operation,)).fetchone()
            grant=json.loads(row[0])if row else {}
            if grant.get('dungeon_clear',[0])[0]!=38300 or grant.get('owner',1001)!=owner:
                raise ValueError('Gate buff owner/receipt')
        if now>=end or source=='spa' and now<start:continue
        result.extend(dict(owner=owner,template=t,start=start,end=end,_environment=True)for t in TEMPLATES[source])
    return result

def _deadline_rows(db,owner,now,table,templates):
    if not exists(db,table):return []
    saved=db.execute(f'SELECT starts_at,ends_at FROM {table} WHERE owner=?',(owner,)).fetchone()
    if saved is None:return []
    start,end=saved
    if not 1<=start<end<2**31 or end-start!=1800:raise ValueError('Rest blessing deadline')
    if not start<=now<end:return []
    return [dict(owner=owner,template=t,start=start,end=end,_environment=True) for t in templates]

def select_rest_buffs(environment,assembly):
    """Select the same active blessing for the native snapshot and settlement."""
    newest=max((r for r in environment if r['template'] in REST_GROUPS),
        key=lambda r:(r['start'],r['template']==FESTIVAL_BUFF),default=None)
    if newest is None:return environment,assembly
    if any(r['start']>newest['start'] for r in assembly):
        return [r for r in environment if r['template'] not in REST_GROUPS],assembly
    active=REST_GROUPS[newest['template']]
    return [r for r in environment if r['template'] in active or r['template'] not in REST_GROUPS],[]

def rest_exp_bonus(db,owner,now,*,dungeon=None):
    """Basis points from a live rest blessing. No dungeon means official PvP."""
    environment=rows(db,owner,now,rest_only=True)
    if not environment:return 0
    from els_server.storage.assembly_state import view
    environment,_=select_rest_buffs(environment,view(db,owner,now)['rows'])
    if any(r['template'] in (964,3083) for r in environment):return 3000
    if dungeon is not None and any(r['template']==FESTIVAL_BUFF for r in environment):
        from els_server.domain.elixir_economy import eligible
        if eligible(dungeon):return 5000
    return 0
