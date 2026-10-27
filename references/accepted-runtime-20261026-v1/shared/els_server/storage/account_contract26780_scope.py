"""Only account-once26780 contract delivery; all old scopes delegate unchanged."""
import hashlib,json,struct
from els_server.storage import account_epic_scope as legacy

QUEST=legacy.QUEST
CONTRACT=26780
MUTATIONS_ENABLED=True
exists=legacy.exists
account=legacy.account

def scoped(qid):return qid==CONTRACT or legacy.scoped(qid)

def _binding(db,uid):
    if not exists(db,'account_contract26780_binding'):return None
    return db.execute('SELECT owner,accepted_action FROM account_contract26780_binding WHERE account=?',(account(db,uid),)).fetchone()

def _carriers(db,uid):
    a=account(db,uid);rows=[]
    for kind,table in (('active','character_quests'),('completed','completed_quests')):
        if exists(db,table):rows.extend((kind,r[0]) for r in db.execute('SELECT q.owner FROM '+table+' q JOIN character_owners o ON o.uid=q.owner WHERE o.account_id=? AND q.quest=?',(a,CONTRACT)))
    return rows

def _acceptance(db,binding):
    from els_server.protocol.quest_messages import request
    owner,generation=binding
    # Reuse the actual EE decoder and the existing action digest construction.
    allowed={hashlib.sha256(json.dumps([owner,'accept',request(0xee,struct.pack('>ii',CONTRACT,npc))],sort_keys=True).encode()).hexdigest() for npc in (10018,10025)}
    row=db.execute('SELECT owner,kind,request_hash FROM quest_actions WHERE rowid=?',(generation,)).fetchone()
    if row is None or row[:2]!=(owner,'accept') or row[2] not in allowed:raise ValueError('Contract26780 accepted action provenance')

def _integrity(db,uid):
    b=_binding(db,uid);rows=_carriers(db,uid)
    if b is None:
        if rows:raise ValueError('Unbound contract26780 history requires review')
    else:
        if account(db,b[0])!=account(db,uid) or len(rows)>1 or any(owner!=b[0] for kind,owner in rows):raise ValueError('Conflicting contract26780 history requires review')
        _acceptance(db,b)
        if rows and rows[0][0]=='active' and db.execute('SELECT generation FROM character_quests WHERE owner=? AND quest=?',(b[0],CONTRACT)).fetchone()!=(b[1],):raise ValueError('Contract26780 active generation mismatch')
    return b

def _view_owner(db,uid):
    b=_binding(db,uid);rows=_carriers(db,uid)
    if len(rows)!=1:return None
    if b is None:return uid if rows[0][1]==uid else None
    try:return b[0] if rows[0][1]==b[0] and account(db,b[0])==account(db,uid) else None
    except ValueError:return None

def quest_owner(db,uid,qid):
    if qid!=CONTRACT:return legacy.quest_owner(db,uid,qid)
    b=_binding(db,uid);return b[0] if b is not None else uid

def active_rows(db,uid):
    rows=[r for r in legacy.active_rows(db,uid) if r[0]!=CONTRACT];owner=_view_owner(db,uid)
    if owner is not None:rows.extend(db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=?',(owner,CONTRACT)))
    return sorted(rows)

def completed_rows(db,uid):
    rows=[r for r in legacy.completed_rows(db,uid) if r[0]!=CONTRACT];owner=_view_owner(db,uid)
    if owner is not None:rows.extend(db.execute('SELECT quest,completed_at FROM completed_quests WHERE owner=? AND quest=?',(owner,CONTRACT)))
    return sorted(rows)

def _actor(db,uid,expected,guard):
    if not db.in_transaction or not callable(guard):raise ValueError('Contract26780 current transaction/session guard required')
    guard(db)
    from els_server.storage.item_actor import require_active_character
    require_active_character(db,uid);a=account(db,uid,expected)
    if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):raise ValueError('Contract26780 current role99 required')
    return a

def before_action(db,uid,expected,kind,guard,*,qid=QUEST):
    if qid!=CONTRACT:return legacy.before_action(db,uid,expected,kind,guard,qid=qid)
    if kind not in ('accept','abandon','claim'):raise ValueError('Contract26780 finite action')
    a=_actor(db,uid,expected,guard);b=_integrity(db,uid)
    done=b is not None and exists(db,'completed_quests') and db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(b[0],CONTRACT)).fetchone() is not None
    if not MUTATIONS_ENABLED and (kind=='accept' or kind=='claim' and not done):raise ValueError('Contract26780 new delivery is held')
    return a

def insert_active(db,uid,qid,now,generation,raw):
    if qid!=CONTRACT:return legacy.insert_active(db,uid,qid,now,generation,raw)
    if not MUTATIONS_ENABLED or not db.in_transaction:raise ValueError('Contract26780 accept unavailable')
    b=_integrity(db,uid);a=account(db,uid)
    if _carriers(db,uid):raise ValueError('Contract26780 already active/completed')
    db.execute('''CREATE TABLE IF NOT EXISTS account_contract26780_binding(
        account INTEGER PRIMARY KEY CHECK(account>0),owner INTEGER NOT NULL REFERENCES characters(uid),
        accepted_action INTEGER NOT NULL CHECK(accepted_action>0))''')
    db.execute('INSERT INTO account_contract26780_binding VALUES(?,?,?) ON CONFLICT(account) DO UPDATE SET owner=excluded.owner,accepted_action=excluded.accepted_action',(a,uid,generation))
    db.execute('INSERT INTO character_quests VALUES(?,?,?,?,?)',(uid,qid,now,generation,raw))

def insert_completed(db,uid,qid,now,reward):
    if qid!=CONTRACT:return legacy.insert_completed(db,uid,qid,now,reward)
    if not MUTATIONS_ENABLED:raise ValueError('Contract26780 unfinished reward unavailable')
    b=_integrity(db,uid)
    if b is None:raise ValueError('Contract26780 binding required')
    saved=dict(reward,account_reward_recipient=uid)
    db.execute('INSERT INTO completed_quests VALUES(?,?,?,?)',(b[0],qid,now,json.dumps(saved,sort_keys=True)))

def reward_row(db,uid,qid):
    if qid!=CONTRACT:return legacy.reward_row(db,uid,qid)
    row=db.execute('SELECT reward_json FROM completed_quests WHERE owner=? AND quest=?',(quest_owner(db,uid,qid),qid)).fetchone()
    return None if row is not None and json.loads(row[0]).get('account_reward_recipient')!=uid else row

def progress_allowed(db,uid,expected,event_id,event,proof,guard,*,qid=QUEST):
    if qid==CONTRACT:return False  # Only the original validated FD writer below.
    return legacy.progress_allowed(db,uid,expected,event_id,event,proof,guard,qid=qid)

def has_active(db,uid):
    owner=_view_owner(db,uid)
    return owner is not None and db.execute('SELECT 1 FROM character_quests WHERE owner=? AND quest=?',(owner,CONTRACT)).fetchone() is not None

def dialogue_source(db,store,active,npc,town):
    if not MUTATIONS_ENABLED or active['id']!=CONTRACT or npc!=10018:raise ValueError('Contract26780 original FD source required')
    a=_actor(db,store.uid,store.account_id,store.account_source_guard);b=_integrity(db,store.uid)
    if b is None or active['owner']!=b[0] or active['generation']!=b[1]:raise ValueError('Contract26780 FD canonical generation')
    if db.execute('SELECT accepted_at,generation FROM character_quests WHERE owner=? AND quest=?',(b[0],CONTRACT)).fetchone()!=(active['accepted_at'],b[1]):raise ValueError('Contract26780 FD generation retired')
    from els_server.domain.town_dialogue import catalog
    if db.execute('SELECT town FROM location WHERE uid=?',(store.uid,)).fetchone()!=(town,) or str(town) not in catalog()['npc_bindings']['10018']['towns']:raise ValueError('Contract26780 current FD scene')
    return dict(accepted_owner=b[0],account=a,actor=store.uid)
