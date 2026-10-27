"""Finite account scope adapter for53520; reuse the existing quest engine.

The original active/completed rows and full reward encoding remain in the
generic engine. One account binding selects their canonical character owner;
read projections share those exact rows without changing their wire owner.
Only qualified accept creates scope tables. No scan backfills past clears.
"""
import hashlib,json,uuid
QUEST=53520

def exists(db,name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()is not None

def account(db,uid,expected=None):
    row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
    if row is None or type(row[0])is not int or row[0]<1 or (expected is not None and row[0]!=expected):
        raise ValueError('ERP support quest owner')
    return row[0]

def binding(db,uid):
    if not exists(db,'erp_support_quest_accounts'):return None
    a=account(db,uid)
    row=db.execute('SELECT owner,reward_floor FROM erp_support_quest_accounts WHERE account=? AND quest=?',(a,QUEST)).fetchone()
    return row

def carriers(db,uid):
    a=account(db,uid);out=[]
    for kind,table in (('active','character_quests'),('completed','completed_quests')):
        if exists(db,table):
            out.extend((kind,r[0])for r in db.execute('SELECT q.owner FROM '+table+' q JOIN character_owners o ON o.uid=q.owner WHERE o.account_id=? AND q.quest=?',(a,QUEST)))
    return out

def require_scope_integrity(db,uid):
    b=binding(db,uid);rows=carriers(db,uid)
    if b is None:
        if rows:raise ValueError('Unbound account ERP support history requires review')
    elif (account(db,b[0])!=account(db,uid)or any(owner!=b[0]for kind,owner in rows)or len(rows)>1):
        raise ValueError('Conflicting account ERP support history requires review')
    return b

def view_owner(db,uid,own_rows):
    if not exists(db,'erp_support_quest_accounts')and not any(r[0]==QUEST for r in own_rows):return None
    b=binding(db,uid);rows=carriers(db,uid)
    # Corrupt/ambiguous source history never gets merged or silently awarded.
    # Keep its raw rows untouched, while ordinary unrelated quests still load.
    if len(rows)>1:return None
    if b is None:return uid if rows and rows[0][1]==uid else None
    if not rows or rows[0][1]!=b[0]:return None
    try:return b[0]if account(db,b[0])==account(db,uid)else None
    except ValueError:return None

def quest_owner(db,uid,qid):
    if qid!=QUEST:return uid
    b=binding(db,uid)
    return b[0]if b is not None else uid

def active_rows(db,uid):
    rows=list(db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=? ORDER BY quest',(uid,)))
    owner=view_owner(db,uid,rows);rows=[r for r in rows if r[0]!=QUEST]
    if owner is not None:rows.extend(db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=?',(owner,QUEST)))
    return sorted(rows)

def completed_rows(db,uid):
    rows=list(db.execute('SELECT quest,completed_at FROM completed_quests WHERE owner=? ORDER BY quest',(uid,)))
    owner=view_owner(db,uid,rows);rows=[r for r in rows if r[0]!=QUEST]
    if owner is not None:rows.extend(db.execute('SELECT quest,completed_at FROM completed_quests WHERE owner=? AND quest=?',(owner,QUEST)))
    return sorted(rows)

def eligible(db,uid,expected,guard):
    if not db.in_transaction or not callable(guard):raise ValueError('ERP support transaction/session guard required')
    guard(db)
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.resonance_state import snapshot
    require_active_character(db,uid);a=account(db,uid,expected)
    row=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()
    er=snapshot(db,uid,a)
    if row!=(99,)or not er['enabled']or er['level']<100:raise ValueError('ERP support level99 and authoritative ERP100 required')
    return a

def before_action(db,uid,expected,kind,guard):
    if kind not in ('accept','abandon','claim'):raise ValueError('ERP support action')
    from els_server.domain.erp_support_quest import catalog
    if not catalog()['source_mutations_enabled']:raise ValueError('ERP support source mutations held for compatibility recovery')
    a=eligible(db,uid,expected,guard);require_scope_integrity(db,uid);return a

def ensure(db):
    if not db.in_transaction:raise ValueError('ERP support scope requires caller transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS erp_support_quest_accounts(
        account INTEGER NOT NULL CHECK(account>0),quest INTEGER NOT NULL CHECK(quest=53520),
        owner INTEGER NOT NULL REFERENCES characters(uid),reward_floor INTEGER NOT NULL CHECK(reward_floor>=0),
        PRIMARY KEY(account,quest))''')
    db.execute('''CREATE TABLE IF NOT EXISTS erp_support_quest_clears(
        account INTEGER NOT NULL,quest INTEGER NOT NULL CHECK(quest=53520),run_id TEXT NOT NULL,
        owner INTEGER NOT NULL,grant_sha256 TEXT NOT NULL,source_proof_sha256 TEXT NOT NULL,
        assessment_sha256 TEXT NOT NULL,PRIMARY KEY(account,quest,run_id))''')

def insert_active(db,uid,qid,now,generation,raw):
    if qid==QUEST:
        a=account(db,uid);b=require_scope_integrity(db,uid);ensure(db)
        if b is not None and (db.execute('SELECT 1 FROM character_quests WHERE owner=? AND quest=?',(b[0],QUEST)).fetchone()
            or db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(b[0],QUEST)).fetchone()):
            raise ValueError('Account ERP support task already active/completed')
        floor=db.execute('SELECT COALESCE(MAX(rowid),0) FROM reward_receipts').fetchone()[0]if exists(db,'reward_receipts')else 0
        db.execute('''INSERT INTO erp_support_quest_accounts VALUES(?,?,?,?)
            ON CONFLICT(account,quest) DO UPDATE SET owner=excluded.owner,reward_floor=excluded.reward_floor''',(a,QUEST,uid,floor))
    db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(uid,qid,now,generation,raw))

def insert_completed(db,uid,qid,now,reward):
    owner=quest_owner(db,uid,qid)
    if qid==QUEST:reward=dict(reward,account_reward_recipient=uid)
    db.execute('INSERT INTO completed_quests VALUES (?,?,?,?)',(owner,qid,now,json.dumps(reward,sort_keys=True)))

def reward_row(db,uid,qid):
    row=db.execute('SELECT reward_json FROM completed_quests WHERE owner=? AND quest=?',(quest_owner(db,uid,qid),qid)).fetchone()
    if qid==QUEST and row is not None and json.loads(row[0]).get('account_reward_recipient')!=uid:
        return None  # Another receiver's items never become this role's delta.
    return row

def progress_allowed(db,uid,expected,event_id,event,proof,guard):
    from els_server.domain.erp_support_quest import catalog
    if not catalog()['source_mutations_enabled']:return False
    if event.get('kind')!='clear'or not event_id.endswith(':clear'):return False
    try:a=eligible(db,uid,expected,guard)
    except ValueError:return False
    require_scope_integrity(db,uid)
    run=event_id[:-6]
    try:
        if str(uuid.UUID(run))!=run:return False
    except (ValueError,TypeError,AttributeError):return False
    b=binding(db,uid)
    if b is None or not exists(db,'reward_receipts'):return False
    row=db.execute('SELECT rowid,proof_sha256,grant_json FROM reward_receipts WHERE run_id=?',(run,)).fetchone()
    if row is None or row[0]<=b[1]:return False
    try:g=json.loads(row[2])
    except (ValueError,TypeError):return False
    pair=g.get('dungeon_clear')
    if (type(g.get('owner',1001))is not int or g.get('owner',1001)!=uid or type(pair)is not list or len(pair)!=2
        or any(type(v)is not int or v<0 for v in pair)or pair[0]!=event['dungeon']):return False
    from els_server.storage.local_clear_rules import lookup_db
    committed=lookup_db(db,uid,run)
    if committed is None:return False
    assessment=committed['assessment']
    if assessment.get('dungeon')!=pair[0]or assessment.get('seconds')!=pair[1]:return False
    from els_server.domain.erp_support_quest import catalog
    from els_server.domain.seal_quests import objective_increment
    if not objective_increment(catalog()['subquests'][str(QUEST)],event,proof):return False
    digest=hashlib.sha256(row[2].encode()).hexdigest()
    adigest=hashlib.sha256(json.dumps(assessment,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    old=db.execute('SELECT owner,grant_sha256,source_proof_sha256,assessment_sha256 FROM erp_support_quest_clears WHERE account=? AND quest=? AND run_id=?',(a,QUEST,run)).fetchone()
    exact=(uid,digest,row[1],adigest)
    if old is not None:
        if old!=exact:raise ValueError('Conflicting committed ERP support clear')
        return False
    db.execute('INSERT INTO erp_support_quest_clears VALUES(?,?,?,?,?,?,?)',(a,QUEST,run,*exact))
    return True
