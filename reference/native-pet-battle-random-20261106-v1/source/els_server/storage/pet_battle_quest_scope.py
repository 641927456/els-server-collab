"""One canonical account weekly task, advanced by sealed random-match results."""
import hashlib,json
from els_server.storage import mentor45000_scope as legacy
from els_server.domain.guild_rules import week
from els_server.domain.pet_battle_quest import QUEST

exists=legacy.exists
account=legacy.account


def scoped(qid):return qid==QUEST or legacy.scoped(qid)


def _binding(db,uid):
    if not exists(db,'account_pet_battle_quest_bindings'):return None
    return db.execute('SELECT owner,accepted_action,result_floor,week FROM account_pet_battle_quest_bindings WHERE account=?',(account(db,uid),)).fetchone()


def _carriers(db,uid):
    rows=[]
    for kind,table in(('active','character_quests'),('done','completed_quests')):
        if exists(db,table):
            rows.extend((kind,r[0])for r in db.execute('SELECT q.owner FROM '+table+' q JOIN character_owners o ON o.uid=q.owner WHERE o.account_id=? AND q.quest=?',(account(db,uid),QUEST)))
    return rows


def _integrity(db,uid):
    binding=_binding(db,uid);rows=_carriers(db,uid)
    if binding is None:
        if rows:raise ValueError('Unbound pet weekly history')
        return None
    owner,generation,floor,period=binding
    if account(db,owner)!=account(db,uid)or len(rows)>1 or any(r[1]!=owner for r in rows):
        raise ValueError('Pet weekly canonical carrier conflict')
    action=db.execute('SELECT owner,kind,request_hash FROM quest_actions WHERE rowid=?',(generation,)).fetchone()
    hashes={hashlib.sha256(json.dumps([owner,'accept',dict(quest=QUEST,npc=npc)],sort_keys=True).encode()).hexdigest()for npc in(10017,10025)}
    if action is None or action[:2]!=(owner,'accept')or action[2]not in hashes:
        raise ValueError('Pet weekly original acceptance source')
    if rows and rows[0][0]=='active':
        active=db.execute('SELECT generation,accepted_at FROM character_quests WHERE owner=? AND quest=?',(owner,QUEST)).fetchone()
        if active[0]!=generation or week(active[1])!=period:raise ValueError('Pet weekly accepted generation changed')
    return binding


def _actor(db,uid,expected,guard):
    if not db.in_transaction or not callable(guard):raise ValueError('Pet weekly current SQL writer required')
    guard(db)
    from els_server.storage.item_actor import require_active_character
    require_active_character(db,uid);identity=account(db,uid,expected)
    if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):
        raise ValueError('Pet weekly original level99')
    return identity


def prepare(store,db,operation,kind,now):
    identity=_actor(db,store.uid,store.account_id,store.account_source_guard)
    binding=_integrity(db,store.uid);period=week(now)
    db.execute('''CREATE TABLE IF NOT EXISTS pet_battle_quest_operations(
        operation TEXT PRIMARY KEY,account INTEGER NOT NULL,owner INTEGER NOT NULL,kind TEXT NOT NULL,week INTEGER NOT NULL)''')
    previous=db.execute('SELECT account,owner,kind,week FROM pet_battle_quest_operations WHERE operation=?',(operation,)).fetchone()
    fact=(identity,store.uid,kind,period)
    if previous is not None and previous!=fact:raise ValueError('Pet weekly request belongs to another generation')
    if binding is not None and binding[3]!=period:
        if binding[3]>period:raise ValueError('Pet weekly clock moved backwards')
        owner=binding[0]
        active=db.execute('SELECT accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=?',(owner,QUEST)).fetchone()
        done=db.execute('SELECT completed_at,reward_json FROM completed_quests WHERE owner=? AND quest=?',(owner,QUEST)).fetchone()
        db.execute('''CREATE TABLE IF NOT EXISTS pet_battle_quest_history(
            account INTEGER NOT NULL,week INTEGER NOT NULL,owner INTEGER NOT NULL,state_json TEXT NOT NULL,
            PRIMARY KEY(account,week))''')
        db.execute('INSERT INTO pet_battle_quest_history VALUES(?,?,?,?)',(identity,binding[3],owner,json.dumps(dict(active=active,completed=done),sort_keys=True)))
        db.execute('DELETE FROM character_quests WHERE owner=? AND quest=?',(owner,QUEST))
        db.execute('DELETE FROM completed_quests WHERE owner=? AND quest=?',(owner,QUEST))
        db.execute('DELETE FROM account_pet_battle_quest_bindings WHERE account=?',(identity,))
    db.execute('INSERT OR IGNORE INTO pet_battle_quest_operations VALUES(?,?,?,?,?)',(operation,*fact))


def before_action(db,uid,expected,kind,guard,*,qid=QUEST):
    if qid!=QUEST:return legacy.before_action(db,uid,expected,kind,guard,qid=qid)
    _actor(db,uid,expected,guard);_integrity(db,uid)


def quest_owner(db,uid,qid):
    if qid!=QUEST:return legacy.quest_owner(db,uid,qid)
    binding=_binding(db,uid)
    return binding[0]if binding else uid


def _view(db,uid):
    binding=_binding(db,uid);rows=_carriers(db,uid)
    if binding is None or len(rows)!=1 or rows[0][1]!=binding[0]:return None
    return binding[0]


def active_rows(db,uid):
    rows=[r for r in legacy.active_rows(db,uid)if r[0]!=QUEST];owner=_view(db,uid)
    if owner is not None:rows.extend(db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=?',(owner,QUEST)))
    return sorted(rows)


def completed_rows(db,uid):
    rows=[r for r in legacy.completed_rows(db,uid)if r[0]!=QUEST];owner=_view(db,uid)
    if owner is not None:rows.extend(db.execute('SELECT quest,completed_at FROM completed_quests WHERE owner=? AND quest=?',(owner,QUEST)))
    return sorted(rows)


def insert_active(db,uid,qid,now,generation,raw):
    if qid!=QUEST:return legacy.insert_active(db,uid,qid,now,generation,raw)
    _integrity(db,uid)
    if _carriers(db,uid):raise ValueError('Pet weekly already active/completed')
    floor=db.execute('SELECT COALESCE(MAX(rowid),0)FROM pet_battle_results').fetchone()[0]if exists(db,'pet_battle_results')else 0
    db.execute('''CREATE TABLE IF NOT EXISTS account_pet_battle_quest_bindings(
        account INTEGER PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),
        accepted_action INTEGER NOT NULL,result_floor INTEGER NOT NULL,week INTEGER NOT NULL)''')
    db.execute('INSERT INTO account_pet_battle_quest_bindings VALUES(?,?,?,?,?) ON CONFLICT(account) DO UPDATE SET owner=excluded.owner,accepted_action=excluded.accepted_action,result_floor=excluded.result_floor,week=excluded.week',(account(db,uid),uid,generation,floor,week(now)))
    db.execute('INSERT INTO character_quests VALUES(?,?,?,?,?)',(uid,qid,now,generation,raw))


def insert_completed(db,uid,qid,now,reward):
    if qid!=QUEST:return legacy.insert_completed(db,uid,qid,now,reward)
    binding=_integrity(db,uid)
    if binding is None:raise ValueError('Pet weekly accepted source required')
    db.execute('INSERT INTO completed_quests VALUES(?,?,?,?)',(binding[0],qid,now,json.dumps(dict(reward,account_reward_recipient=uid),sort_keys=True)))


def reward_row(db,uid,qid):
    if qid!=QUEST:return legacy.reward_row(db,uid,qid)
    row=db.execute('SELECT reward_json FROM completed_quests WHERE owner=? AND quest=?',(quest_owner(db,uid,qid),qid)).fetchone()
    return None if row and json.loads(row[0]).get('account_reward_recipient')!=uid else row


def progress_allowed(db,uid,expected,event_id,event,proof,guard,*,qid=QUEST):
    if qid==QUEST:return False
    return legacy.progress_allowed(db,uid,expected,event_id,event,proof,guard,qid=qid)


def record(db,uid,expected,match,guard,now):
    binding=_integrity(db,uid)
    if binding is None or binding[3]!=week(now):return []
    active=db.execute('SELECT generation,objectives FROM character_quests WHERE owner=? AND quest=?',(binding[0],QUEST)).fetchone()
    if active is None:return []
    _actor(db,uid,expected,guard)
    source=db.execute('SELECT rowid,winner,account,ended_at,fact_json FROM pet_battle_results WHERE match_id=?',(match,)).fetchone()
    if source is None or source[1:3]!=(uid,expected):raise ValueError('Pet weekly sealed winner receipt required')
    fact=json.loads(source[4])
    if fact['mode']!='random' or fact['winner']!=uid:raise ValueError('Pet weekly random winner source')
    if source[0]<=binding[2]or week(source[3])!=binding[3]:return []
    event_id='pet-battle-win:'+match
    digest=hashlib.sha256(source[4].encode()).hexdigest()
    previous=db.execute('SELECT proof_hash FROM quest_progress_events WHERE owner=? AND event_id=?',(uid,event_id)).fetchone()
    if previous is not None:
        if previous!=(digest,):raise ValueError('Pet weekly result retry changed')
        return []
    counts=json.loads(active[1]);value=counts[str(QUEST)]
    if set(counts)!={str(QUEST)}or type(value)is not int or not 0<=value<=3:
        raise ValueError('Pet weekly persisted objective source')
    if value>=3:return []
    counts[str(QUEST)]=value+1
    if db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=? AND generation=?',(json.dumps(counts,sort_keys=True),binding[0],QUEST,active[0])).rowcount!=1:
        raise ValueError('Pet weekly accepted generation changed during progress')
    db.execute('INSERT INTO quest_progress_events VALUES(?,?,?,?)',(uid,event_id,digest,source[4]))
    from els_server.protocol.quest_messages import progress
    from els_server.protocol.protocol_codec import encode_event
    event=progress([dict(id=QUEST,owner=binding[0],projection_owner=uid,generation=active[0],objectives={QUEST:value+1})])
    encode_event(event);_actor(db,uid,expected,guard)
    return [event]


def grant(store,db,operation,now):
    from els_server.domain import pet_battle_quest as rules
    from els_server.domain.raid_reward_items import _issue_source
    from els_server.storage.inventory_state import grant_items
    binding=_integrity(db,store.uid)
    if binding is None or binding[3]!=week(now):raise ValueError('Pet weekly current accepted week required')
    def guard(writer):
        _actor(writer,store.uid,store.account_id,store.account_source_guard)
        if _integrity(writer,store.uid)!=binding:raise ValueError('Pet weekly source changed before grant')
        return True
    plan=rules.reward_plan()
    source=_issue_source(db,store.uid,operation,'ordinary',dict(policy=rules.POLICY,owner=store.uid,
        quest=QUEST,account=store.account_id,week=binding[3],generation=binding[1],definition_sha256=rules.DATA_SHA),plan,guard)
    return grant_items(db,plan,store.uid,raid_reward_source=source)
