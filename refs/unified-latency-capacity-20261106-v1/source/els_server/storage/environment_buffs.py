"""Earned spa and Gate of Darkness deadlines, in the original source writer."""
import json,time

def exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='environment_buff_sources'").fetchone() is not None

def put(db,owner,source,operation,now):
    if not db.in_transaction:raise ValueError('Environment buff requires source transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS environment_buff_sources(
        owner INTEGER NOT NULL REFERENCES characters(uid),source TEXT NOT NULL,
        starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,operation_id TEXT NOT NULL,
        PRIMARY KEY(owner,source))''')
    db.execute('''INSERT INTO environment_buff_sources VALUES(?,?,?,?,?)
        ON CONFLICT(owner,source)DO UPDATE SET starts_at=excluded.starts_at,
        ends_at=excluded.ends_at,operation_id=excluded.operation_id''',
        (owner,source,now,now+1800,operation))

def gate_clear(db,owner,run_id):
    # RewardState calls this only for a new committed38300 full-clear receipt.
    row=db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(run_id,)).fetchone()
    if row is None or json.loads(row[0]).get('dungeon_clear',[0])[0]!=38300:
        raise ValueError('Gate buff requires the original clear receipt')
    put(db,owner,'gate',run_id,int(time.time()))

def rows(db,owner,now):
    if not exists(db):return []
    result=[]
    for source,start,end,operation in db.execute('SELECT source,starts_at,ends_at,operation_id FROM environment_buff_sources WHERE owner=?',(owner,)):
        if source not in ('spa','gate')or not 1<=start<end<2**31 or end-start!=1800:
            raise ValueError('Environment buff save')
        if source=='gate':
            row=db.execute('SELECT grant_json FROM reward_receipts WHERE run_id=?',(operation,)).fetchone()
            grant=json.loads(row[0])if row else {}
            if grant.get('dungeon_clear',[0])[0]!=38300 or grant.get('owner',1001)!=owner:
                raise ValueError('Gate buff owner/receipt')
        if now>=end:continue
        templates=(202,)if source=='gate'else(964,965)
        result.extend(dict(owner=owner,template=t,start=start,end=end,_environment=True)for t in templates)
    return result
