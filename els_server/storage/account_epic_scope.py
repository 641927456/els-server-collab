"""Only four new AccountQuest scopes; preserve the published53520 adapter.

Original quest rows remain canonical character rows. A finite account binding
shares their projections and protects one current reward recipient. This does
not migrate history or enable another AccountQuest identity.
"""
import hashlib,json,uuid
from els_server.storage import erp_support_quest_scope as legacy

QUEST=legacy.QUEST
NEW_QUESTS=frozenset((37100,53500,53510,53530))
MIN_ERP={53500:10,53510:50,53530:150}
exists=legacy.exists
account=legacy.account

def scoped(qid):return qid==QUEST or qid in NEW_QUESTS

def _binding(db,uid,qid):
    if not exists(db,'account_epic_scope_accounts'):return None
    return db.execute('SELECT owner,reward_floor FROM account_epic_scope_accounts WHERE account=? AND quest=?',(account(db,uid),qid)).fetchone()

def _carriers(db,uid,qid):
    a=account(db,uid);rows=[]
    for kind,table in (('active','character_quests'),('completed','completed_quests')):
        if exists(db,table):rows.extend((kind,r[0]) for r in db.execute('SELECT q.owner FROM '+table+' q JOIN character_owners o ON o.uid=q.owner WHERE o.account_id=? AND q.quest=?',(a,qid)))
    return rows

def _integrity(db,uid,qid):
    binding=_binding(db,uid,qid);rows=_carriers(db,uid,qid)
    if binding is None:
        if rows:raise ValueError('Unbound account Epic history requires review')
    elif account(db,binding[0])!=account(db,uid) or any(owner!=binding[0] for kind,owner in rows) or len(rows)>1:
        raise ValueError('Conflicting account Epic history requires review')
    return binding

def _view_owner(db,uid,qid):
    binding=_binding(db,uid,qid);rows=_carriers(db,uid,qid)
    if len(rows)>1:return None
    if binding is None:return uid if rows and rows[0][1]==uid else None
    if not rows or rows[0][1]!=binding[0]:return None
    try:return binding[0] if account(db,binding[0])==account(db,uid) else None
    except ValueError:return None

def quest_owner(db,uid,qid):
    if qid not in NEW_QUESTS:return legacy.quest_owner(db,uid,qid)
    binding=_binding(db,uid,qid)
    return binding[0] if binding is not None else uid

def active_rows(db,uid):
    rows=[r for r in legacy.active_rows(db,uid) if r[0] not in NEW_QUESTS]
    for qid in sorted(NEW_QUESTS):
        owner=_view_owner(db,uid,qid)
        if owner is not None:rows.extend(db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=?',(owner,qid)))
    return sorted(rows)

def completed_rows(db,uid):
    rows=[r for r in legacy.completed_rows(db,uid) if r[0] not in NEW_QUESTS]
    for qid in sorted(NEW_QUESTS):
        owner=_view_owner(db,uid,qid)
        if owner is not None:rows.extend(db.execute('SELECT quest,completed_at FROM completed_quests WHERE owner=? AND quest=?',(owner,qid)))
    return sorted(rows)

def _eligible(db,uid,expected,guard,qid):
    if qid not in NEW_QUESTS or not db.in_transaction or not callable(guard):raise ValueError('Finite account Epic transaction/session guard required')
    guard(db)
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.resonance_state import snapshot
    require_active_character(db,uid);a=account(db,uid,expected)
    if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):raise ValueError('Account Epic requires current role99')
    er=snapshot(db,uid,a)
    if qid in MIN_ERP and (not er['enabled'] or er['level']<MIN_ERP[qid]):raise ValueError('Account Epic authoritative ERP requirement')
    return a

def before_action(db,uid,expected,kind,guard,*,qid=QUEST):
    if qid==QUEST:return legacy.before_action(db,uid,expected,kind,guard)
    if qid not in NEW_QUESTS or kind not in ('accept','abandon','claim'):raise ValueError('Finite account Epic action')
    from els_server.domain.account_epic_quests import catalog
    if qid not in catalog()['source_mutations_enabled']:raise ValueError('Account Epic source not qualified for mutation')
    a=_eligible(db,uid,expected,guard,qid);_integrity(db,uid,qid);return a

def _ensure(db):
    if not db.in_transaction:raise ValueError('Account Epic scope requires caller transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS account_epic_scope_accounts(
        account INTEGER NOT NULL CHECK(account>0),quest INTEGER NOT NULL CHECK(quest IN(37100,53500,53510,53530)),
        owner INTEGER NOT NULL REFERENCES characters(uid),reward_floor INTEGER NOT NULL CHECK(reward_floor>=0),PRIMARY KEY(account,quest))''')
    db.execute('''CREATE TABLE IF NOT EXISTS account_epic_scope_clears(
        account INTEGER NOT NULL,quest INTEGER NOT NULL CHECK(quest IN(37100,53500,53510,53530)),run_id TEXT NOT NULL,
        owner INTEGER NOT NULL,grant_sha256 TEXT NOT NULL,source_proof_sha256 TEXT NOT NULL,assessment_sha256 TEXT NOT NULL,
        PRIMARY KEY(account,quest,run_id))''')

def insert_active(db,uid,qid,now,generation,raw):
    if qid not in NEW_QUESTS:return legacy.insert_active(db,uid,qid,now,generation,raw)
    a=account(db,uid);binding=_integrity(db,uid,qid);_ensure(db)
    if binding is not None and (db.execute('SELECT 1 FROM character_quests WHERE owner=? AND quest=?',(binding[0],qid)).fetchone() or db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(binding[0],qid)).fetchone()):raise ValueError('Account Epic already active/completed')
    floor=db.execute('SELECT COALESCE(MAX(rowid),0) FROM reward_receipts').fetchone()[0] if exists(db,'reward_receipts') else 0
    db.execute('INSERT INTO account_epic_scope_accounts VALUES(?,?,?,?) ON CONFLICT(account,quest) DO UPDATE SET owner=excluded.owner,reward_floor=excluded.reward_floor',(a,qid,uid,floor))
    db.execute('INSERT INTO character_quests VALUES(?,?,?,?,?)',(uid,qid,now,generation,raw))

def insert_completed(db,uid,qid,now,reward):
    if qid not in NEW_QUESTS:return legacy.insert_completed(db,uid,qid,now,reward)
    a=account(db,uid);_integrity(db,uid,qid)
    reward=dict(reward,account_reward_recipient=uid)
    if qid==37100:
        from els_server.storage.resonance_state import snapshot,ensure
        before=snapshot(db,uid,a)
        if not before['enabled']:
            ensure(db)
            db.execute('INSERT INTO account_resonance VALUES(?,1,0,1) ON CONFLICT(account_id) DO UPDATE SET enabled=1,revision=account_resonance.revision+1 WHERE account_resonance.enabled=0',(a,))
        reward.update(resonance_unlock_quest=37100,enabled_changed=not before['enabled'])
    db.execute('INSERT INTO completed_quests VALUES(?,?,?,?)',(quest_owner(db,uid,qid),qid,now,json.dumps(reward,sort_keys=True)))

def reward_row(db,uid,qid):
    if qid not in NEW_QUESTS:return legacy.reward_row(db,uid,qid)
    row=db.execute('SELECT reward_json FROM completed_quests WHERE owner=? AND quest=?',(quest_owner(db,uid,qid),qid)).fetchone()
    return None if row is not None and json.loads(row[0]).get('account_reward_recipient')!=uid else row

def progress_allowed(db,uid,expected,event_id,event,proof,guard,*,qid=QUEST):
    if qid==QUEST:return legacy.progress_allowed(db,uid,expected,event_id,event,proof,guard)
    if qid not in NEW_QUESTS:return False
    from els_server.domain.account_epic_quests import catalog
    if qid not in catalog()['source_mutations_enabled'] or event.get('kind')!='clear' or not event_id.endswith(':clear'):return False
    try:a=_eligible(db,uid,expected,guard,qid)
    except ValueError:return False
    _integrity(db,uid,qid);binding=_binding(db,uid,qid);run=event_id[:-6]
    try:
        if str(uuid.UUID(run))!=run:return False
    except (ValueError,TypeError,AttributeError):return False
    if binding is None or not exists(db,'reward_receipts'):return False
    row=db.execute('SELECT rowid,proof_sha256,grant_json FROM reward_receipts WHERE run_id=?',(run,)).fetchone()
    if row is None or row[0]<=binding[1]:return False
    try:grant=json.loads(row[2])
    except (ValueError,TypeError):return False
    pair=grant.get('dungeon_clear')
    if (type(grant.get('owner',1001)) is not int or grant.get('owner',1001)!=uid or type(pair) is not list or len(pair)!=2 or any(type(v) is not int or v<0 for v in pair) or pair[0]!=event['dungeon']):return False
    from els_server.storage.local_clear_rules import lookup_db
    committed=lookup_db(db,uid,run)
    if committed is None:return False
    assessment=committed['assessment']
    if assessment.get('dungeon')!=pair[0] or assessment.get('seconds')!=pair[1]:return False
    from els_server.domain.seal_quests import objective_increment,quest_catalog
    if not any(objective_increment(sub,event,proof) for sub in quest_catalog().objectives(qid)):return False
    digest=hashlib.sha256(row[2].encode()).hexdigest();adigest=hashlib.sha256(json.dumps(assessment,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    exact=(uid,digest,row[1],adigest)
    old=db.execute('SELECT owner,grant_sha256,source_proof_sha256,assessment_sha256 FROM account_epic_scope_clears WHERE account=? AND quest=? AND run_id=?',(a,qid,run)).fetchone()
    if old is not None:
        if old!=exact:raise ValueError('Conflicting account Epic committed clear')
        return False
    db.execute('INSERT INTO account_epic_scope_clears VALUES(?,?,?,?,?,?,?)',(a,qid,run,*exact))
    return True
