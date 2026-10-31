"""Same-transaction finite52700 activation and account highest-job ledger."""
from els_server.domain.el_search_collection import QUEST,COST,canonical,current_entry,priority,wire

# Recovery variants replace this one constant; optional readers always remain.
WRITES_ENABLED=True
ACT='character_search_collection_activation'
REG='account_search_collection_registration'

def exists(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def identity(db,uid,account_id):
    if type(account_id)is not int or not 1<=account_id<2**63:raise ValueError('Collection account identity')
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Collection character owner mismatch')

def before_action(db,uid,account_id,kind,guard):
    identity(db,uid,account_id)
    if not callable(guard):raise ValueError('Collection requires current actor lease')
    guard(db)
    # A done claim is a reader/replay even when this finite writer is held.
    completed=exists(db,'completed_quests') and db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(uid,QUEST)).fetchone()
    if not WRITES_ENABLED and kind!='abandon' and not(kind=='claim'and completed):raise ValueError('Collection52700 writer held')

def snapshot(db,uid,account_id):
    identity(db,uid,account_id)
    activated=None
    if exists(db,ACT):
        activated=db.execute('SELECT account_id,source_quest,unit_type,unit_line,unit_class,transcendental,collection_stage,created_at FROM character_search_collection_activation WHERE owner=?',(uid,)).fetchone()
        if activated:
            if activated[0]!=account_id or activated[1]!=QUEST or type(activated[7])is not int or not 0<activated[7]<2**63:raise ValueError('Collection activation integrity')
            canonical(dict(zip(('unit_type','line','unit_class','transcendental','stage'),activated[2:7])))
    rows=[]
    if exists(db,REG):
        for unit,line,cls,trans,stage,recipient,at in db.execute('SELECT unit_type,unit_line,unit_class,transcendental,collection_stage,registered_by,updated_at FROM account_search_collection_registration WHERE account_id=? ORDER BY unit_type,unit_line',(account_id,)):
            identity(db,recipient,account_id)
            if type(at)is not int or not 0<at<2**63:raise ValueError('Collection registration time')
            rows.append(canonical(dict(unit_type=unit,line=line,unit_class=cls,transcendental=trans,stage=stage)))
    if activated is None and not rows:return None
    if activated and not any((r['unit_type'],r['line'])==activated[2:4]and priority(r)>=priority(canonical(dict(zip(('unit_type','line','unit_class','transcendental','stage'),activated[2:7]))))for r in rows):raise ValueError('Collection activation missing account canonical')
    from els_server.storage.el_search_collection_tickets import expiry
    value=dict(active=bool(activated),registered=rows,expiry=expiry(db,uid,account_id),expansion=0,field1d=1,field21=1)
    wire(value)
    return value

def ensure(db):
    if not db.in_transaction:raise ValueError('Collection requires caller transaction')
    db.execute('CREATE TABLE IF NOT EXISTS character_search_collection_activation (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),source_quest INTEGER NOT NULL CHECK(source_quest=52700),unit_type INTEGER NOT NULL CHECK(unit_type BETWEEN 1 AND 15),unit_line INTEGER NOT NULL CHECK(unit_line BETWEEN 1 AND 4),unit_class INTEGER NOT NULL,transcendental INTEGER NOT NULL CHECK(transcendental BETWEEN 0 AND 2),collection_stage INTEGER NOT NULL CHECK(collection_stage BETWEEN 1 AND 3),created_at INTEGER NOT NULL CHECK(created_at>0))')
    db.execute('CREATE TABLE IF NOT EXISTS account_search_collection_registration (account_id INTEGER NOT NULL CHECK(account_id>0),unit_type INTEGER NOT NULL CHECK(unit_type BETWEEN 1 AND 15),unit_line INTEGER NOT NULL CHECK(unit_line BETWEEN 1 AND 4),unit_class INTEGER NOT NULL,transcendental INTEGER NOT NULL CHECK(transcendental BETWEEN 0 AND 2),collection_stage INTEGER NOT NULL CHECK(collection_stage BETWEEN 1 AND 3),registered_by INTEGER NOT NULL REFERENCES characters(uid),updated_at INTEGER NOT NULL CHECK(updated_at>0),PRIMARY KEY(account_id,unit_type,unit_line))')

def _register(db,uid,account_id,value,now):
    canonical(value)
    old=db.execute('SELECT unit_class,transcendental,collection_stage FROM account_search_collection_registration WHERE account_id=? AND unit_type=? AND unit_line=?',(account_id,value['unit_type'],value['line'])).fetchone()
    if old:
        previous=canonical(dict(unit_type=value['unit_type'],line=value['line'],unit_class=old[0],transcendental=old[1],stage=old[2]))
        if priority(previous)>=priority(value):return False
    db.execute('INSERT INTO account_search_collection_registration VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(account_id,unit_type,unit_line) DO UPDATE SET unit_class=excluded.unit_class,transcendental=excluded.transcendental,collection_stage=excluded.collection_stage,registered_by=excluded.registered_by,updated_at=excluded.updated_at',(account_id,value['unit_type'],value['line'],value['unit_class'],value['transcendental'],value['stage'],uid,now))
    return True

def activate(db,uid,account_id,character,now):
    if not WRITES_ENABLED:raise ValueError('Collection52700 writer held')
    identity(db,uid,account_id)
    if character['uid']!=uid or character['level']<99 or type(now)is not int or not 0<now<2**63:raise ValueError('Collection activation eligibility')
    before=snapshot(db,uid,account_id)
    if before is not None and before['active']:raise ValueError('Collection already activated')
    value=current_entry(character)
    from els_server.storage.ep_points import debit
    debit(db,uid,COST);ensure(db)
    db.execute('INSERT INTO character_search_collection_activation VALUES (?,?,?,?,?,?,?,?,?)',(uid,account_id,QUEST,value['unit_type'],value['line'],value['unit_class'],value['transcendental'],value['stage'],now))
    _register(db,uid,account_id,value,now)
    return snapshot(db,uid,account_id)

def career_changed(db,uid,character):
    # Only a proven existing career writer calls this after its saved change.
    # Never activate, spend EP or create an account entry for an unopened role.
    if not WRITES_ENABLED or not exists(db,ACT):return False
    row=db.execute('SELECT account_id FROM character_search_collection_activation WHERE owner=?',(uid,)).fetchone()
    if row is None:return False
    identity(db,uid,row[0]);snapshot(db,uid,row[0])
    import time
    changed=_register(db,uid,row[0],current_entry(character),int(time.time()))
    snapshot(db,uid,row[0])  # Validate/encode the complete new DTO field before caller commit.
    return changed
