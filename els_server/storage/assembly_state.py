"""Source-owned camp grants and atomic ED debit; no installation migration."""
from contextlib import closing
import hashlib,json,sqlite3,time
from els_server.domain.assembly_rules import POLICY,catalog,source_row,uniform,quote
from els_server.protocol.assembly_messages import request,acknowledgement
from els_server.protocol.protocol_codec import encode_event

def exists(db,name):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def clock(now=None):
    value=int(time.time())if now is None else now
    if type(value)is not int or not 1<=value<2**31-7200:raise ValueError('Assembly epoch bounds')
    return value

def owner(db,uid,account_id):
    from els_server.storage.profession_state import require_owner
    from els_server.storage.item_actor import require_active_character
    require_owner(db,uid,account_id);require_active_character(db,uid)

def view(db,uid,now):
    now=clock(now)
    if not exists(db,'assembly_buffs'):return dict(owner=uid,revision=0,start=0,end=0,rows=[],_moment=now)
    row=db.execute('SELECT revision,starts_at,ends_at,operation_id FROM assembly_buffs WHERE owner=?',(uid,)).fetchone()
    if row is None:return dict(owner=uid,revision=0,start=0,end=0,rows=[],_moment=now)
    revision,start,end,operation=row
    if(any(type(v)is not int for v in(revision,start,end))or not 1<=revision<2**63
       or not 1<=start<end<2**31 or end-start!=1800 or not exists(db,'assembly_receipts')):raise ValueError('Unqualified assembly save')
    proof=db.execute('SELECT owner,policy,kind,starts_at,ends_at,revision FROM assembly_receipts WHERE operation_id=?',(operation,)).fetchone()
    if proof is None or proof[0]!=uid or proof[1]!=POLICY or proof[2]not in('purchase','stay')or proof[3:]!=(start,end,revision):raise ValueError('Assembly original grant receipt')
    if now<start:raise ValueError('Assembly future stored grant')
    result=dict(owner=uid,revision=revision,start=start,end=end,_moment=now)
    result['rows']=[source_row(uid,result)]if now<end else []
    return result

def _ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS assembly_buffs(
      owner INTEGER PRIMARY KEY REFERENCES characters(uid),revision INTEGER NOT NULL,
      starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,operation_id TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS assembly_receipts(
      operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL,policy TEXT NOT NULL,
      kind TEXT NOT NULL,request_sha256 TEXT NOT NULL,town INTEGER NOT NULL,
      uniform_division INTEGER NOT NULL,ed_cost INTEGER NOT NULL,starts_at INTEGER NOT NULL,
      ends_at INTEGER NOT NULL,revision INTEGER NOT NULL)''')

def grant(path,uid,account_id,operation,kind,payload,guard,prepare,*,now=None):
    if kind not in('purchase','stay')or not isinstance(operation,str)or not 1<=len(operation)<=160:raise ValueError('Assembly operation')
    if kind=='purchase':request(payload)
    elif not isinstance(payload,bytes)or len(payload)!=32:raise ValueError('Assembly online source proof')
    digest=hashlib.sha256(payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');moment=clock(now)
        owner(db,uid,account_id);facts=guard(db,moment)
        from els_server.storage.inventory_state import load_items
        from els_server.storage.seal_quests import load_character
        from els_server.storage.npc_trade import balances
        character=load_character(db,uid,account_id);items=load_items(db,uid)
        division=uniform(items,character,moment);cost=quote(division)[0]if kind=='purchase'else 0
        old=view(db,uid,moment);balance=balances(db,uid)
        prior=db.execute('SELECT owner,policy,kind,request_sha256 FROM assembly_receipts WHERE operation_id=?',(operation,)).fetchone()if exists(db,'assembly_receipts')else None
        if prior is not None:
            if prior!=(uid,POLICY,kind,digest):raise ValueError('Conflicting assembly retry')
            events=([acknowledgement(balance['ed'])]if kind=='purchase'else [])+prepare(db,old,items)
            for event in events:encode_event(event)
            guard(db,moment)
            return dict(events=events,state=old,replayed=True,division=division)
        if not catalog()['admissions_enabled']:raise ValueError('Assembly new source disabled')
        if balance['ed']<cost:raise ValueError('Assembly ED insufficient')
        if cost and balance['revision']>=2**63-1:raise ValueError('Assembly balance revision overflow')
        revision=old['revision']+1
        if revision>=2**63:raise ValueError('Assembly revision overflow')
        state=dict(owner=uid,revision=revision,start=moment,end=moment+1800,_moment=moment)
        state['rows']=[source_row(uid,state)]
        events=([acknowledgement(balance['ed']-cost)]if kind=='purchase'else [])+prepare(db,state,items)
        for event in events:encode_event(event)
        # The same writer, actor, uniform and exact native scene still own this
        # operation after all packet/profile encoders have completed.
        if guard(db,moment)!=facts or uniform(load_items(db,uid),load_character(db,uid,account_id),moment)!=division:raise ValueError('Assembly source changed before commit')
        _ensure(db)
        if cost and db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=? AND ed=? AND revision=?',(cost,uid,balance['ed'],balance['revision'])).rowcount!=1:raise ValueError('Assembly balance changed')
        db.execute('INSERT INTO assembly_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?)',(operation,uid,POLICY,kind,digest,facts['town'],division,cost,moment,moment+1800,revision))
        db.execute('INSERT INTO assembly_buffs VALUES(?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET revision=excluded.revision,starts_at=excluded.starts_at,ends_at=excluded.ends_at,operation_id=excluded.operation_id',(uid,revision,moment,moment+1800,operation))
        return dict(events=events,state=state,replayed=False,division=division)
