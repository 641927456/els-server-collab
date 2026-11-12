"""Earned spa and Gate of Darkness deadlines, in the original source writer."""
import json,time

FESTIVAL_BUFF = 3456
FESTIVAL_TABLE = 'festival_buff_deadlines'
TEMPLATES = {'gate':(202,), 'spa':(964,965)}

def exists(db,table='environment_buff_sources'):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None

def put(db,owner,source,operation,now):
    if not db.in_transaction:raise ValueError('Environment buff requires source transaction')
    if source=='festival':
        # Older readers still see only their existing spa and Gate sources.
        db.execute('''CREATE TABLE IF NOT EXISTS festival_buff_deadlines(
            owner INTEGER PRIMARY KEY REFERENCES characters(uid), starts_at INTEGER NOT NULL,
            ends_at INTEGER NOT NULL, operation_id TEXT NOT NULL)''')
        db.execute('''INSERT INTO festival_buff_deadlines VALUES(?,?,?,?)
            ON CONFLICT(owner)DO UPDATE SET starts_at=excluded.starts_at,
            ends_at=excluded.ends_at,operation_id=excluded.operation_id''',(owner,now,now+1800,operation))
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

def rows(db,owner,now):
    festival=festival_row(db,owner,now)
    result=[festival] if festival is not None else []
    if not exists(db):return result
    for source,start,end,operation in db.execute('SELECT source,starts_at,ends_at,operation_id FROM environment_buff_sources WHERE owner=?',(owner,)):
        if source not in TEMPLATES or not 1<=start<end<2**31 or end-start!=1800:
            raise ValueError('Environment buff save')
        if source=='gate':
            row=db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(operation,)).fetchone()
            grant=json.loads(row[0])if row else {}
            if grant.get('dungeon_clear',[0])[0]!=38300 or grant.get('owner',1001)!=owner:
                raise ValueError('Gate buff owner/receipt')
        if now>=end:continue
        result.extend(dict(owner=owner,template=t,start=start,end=end,_environment=True)for t in TEMPLATES[source])
    return result

def festival_row(db,owner,now):
    if not exists(db,FESTIVAL_TABLE):return None
    saved=db.execute('SELECT starts_at,ends_at FROM festival_buff_deadlines WHERE owner=?',(owner,)).fetchone()
    if saved is None:return None
    start,end=saved
    if not 1<=start<end<2**31 or end-start!=1800:raise ValueError('Festival buff deadline')
    if start<=now<end:return dict(owner=owner,template=FESTIVAL_BUFF,start=start,end=end,_environment=True)

def select_rest_buffs(environment,assembly):
    """Use the latest blessing when the festival competes with spa or camp."""
    festival=next((row for row in environment if row['template']==FESTIVAL_BUFF),None)
    if festival is None:return environment,assembly
    other=[row for row in environment if row['template'] in TEMPLATES['spa']]+assembly
    if any(row['start']>festival['start'] for row in other):
        return [row for row in environment if row is not festival],assembly
    return [row for row in environment if row['template'] not in TEMPLATES['spa']],[]

def festival_exp_bonus(db,owner,dungeon,now):
    from els_server.domain.elixir_economy import eligible
    if festival_row(db,owner,now) is None or not eligible(dungeon):return 0
    from els_server.storage.assembly_state import view
    environment,_=select_rest_buffs(rows(db,owner,now),view(db,owner,now)['rows'])
    return 5000 if any(row['template']==FESTIVAL_BUFF for row in environment) else 0
