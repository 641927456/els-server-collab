"""Mentor repeat generations and counters inside the original source writer."""
import json,time
from els_server.domain import mentor_quests as rules
from els_server.storage import mentor_relations as relations


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def actor(store,db,qid,kind):
    if not callable(store.account_source_guard):raise ValueError('Mentor task current actor required')
    getattr(store.account_source_guard,'mentor_guard',store.account_source_guard)(db)
    relations.require_owner(db,store.uid,store.account_id)
    from els_server.storage.item_actor import require_active_character
    require_active_character(db,store.uid)
    if kind=='abandon':return
    expected=0 if rules.teacher(qid)else 1
    if relations.role(db,store.uid,store.account_id)!=expected:raise ValueError('Mentor task role requirement')
    own=relations.character(db,uid=store.uid)
    if expected==1 and own['level']>=99:raise ValueError('Student task ends at99')
    if kind=='claim':
        saved=relations.relation(db,store.uid)
        if saved is None or saved['is_student']!=(expected==1):raise ValueError('Mentor task requires a current relationship')
        student=store.uid if expected==1 else saved['partner']
        if relations.character(db,uid=student)['level']>=99:raise ValueError('Mentor task student has graduated')


def _ensure(db):
    if not db.in_transaction:raise ValueError('Mentor task caller writer required')
    db.execute('''CREATE TABLE IF NOT EXISTS native_mentor_quest_cycles(
        owner INTEGER NOT NULL REFERENCES characters(uid),quest INTEGER NOT NULL,cycle INTEGER NOT NULL,
        PRIMARY KEY(owner,quest))''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_mentor_quest_operations(
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,quest INTEGER NOT NULL,kind TEXT NOT NULL,cycle INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_mentor_quest_history(
        owner INTEGER NOT NULL,quest INTEGER NOT NULL,cycle INTEGER NOT NULL,completed_at INTEGER NOT NULL,reward_json TEXT NOT NULL,
        PRIMARY KEY(owner,quest,cycle))''')


def cycle(db,owner,qid):
    row=db.execute('SELECT cycle FROM native_mentor_quest_cycles WHERE owner=?AND quest=?',(owner,qid)).fetchone()
    return row[0]if row is not None else 0


def before_action(store,db,qid,operation,kind,now):
    actor(store,db,qid,kind);_ensure(db)
    value=cycle(db,store.uid,qid)
    old=db.execute('SELECT owner,quest,kind,cycle FROM native_mentor_quest_operations WHERE operation=?',(operation,)).fetchone()
    if old is not None:
        if old!=(store.uid,qid,kind,value):raise ValueError('Mentor task operation belongs to another cycle')
        return
    if rules.teacher(qid)and kind=='accept':
        done=db.execute('SELECT completed_at,reward_json FROM completed_quests WHERE owner=?AND quest=?',(store.uid,qid)).fetchone()
        if done is not None:
            db.execute('INSERT INTO native_mentor_quest_history VALUES(?,?,?,?,?)',(store.uid,qid,value,*done))
            value+=1
            db.execute('DELETE FROM completed_quests WHERE owner=?AND quest=?',(store.uid,qid))
            db.execute('INSERT INTO native_mentor_quest_cycles VALUES(?,?,?)ON CONFLICT(owner,quest)DO UPDATE SET cycle=excluded.cycle',(store.uid,qid,value))


def after_action(store,db,qid,operation,kind,now):
    actor(store,db,qid,kind)
    db.execute('INSERT OR IGNORE INTO native_mentor_quest_operations VALUES(?,?,?,?,?)',
        (operation,store.uid,qid,kind,cycle(db,store.uid,qid)))


def grant(store,db,qid,operation,now):
    from els_server.domain.raid_reward_items import _issue_source
    from els_server.storage.inventory_state import grant_items
    plan=rules.reward_plan(qid,now)
    def guard(writer):
        actor(store,writer,qid,'claim')
        return True
    identity=dict(policy=rules.POLICY,owner=store.uid,quest=qid,at=now,
        cycle=cycle(db,store.uid,qid),definition_sha256=rules.DATA_SHA)
    source=_issue_source(db,store.uid,operation,'ordinary',identity,plan,guard)
    return grant_items(db,plan,store.uid,raid_reward_source=source)


def record(db,owner,operation,fact,activity,guard):
    """Only a sealed shared clear, random mission or opponent result calls this."""
    if not db.in_transaction or guard(db)is not True:raise ValueError('Mentor task original writer required')
    saved=relations.relation(db,owner)
    if (saved is None or saved['generation']!=fact['generation']
            or {owner,saved['partner']}!={fact['student'],fact['teacher']} or fact['student_level']>=99):return []
    if activity['kind']not in('clear','random','duel','black_gate'):raise ValueError('Mentor task original activity kind')
    from els_server.storage.seal_quests import _state
    rows=_state(db,owner,None,progress_only=True,quest_ids=set(map(int,rules.catalog()['quests'])))['active']
    if not rows:return []
    db.execute('''CREATE TABLE IF NOT EXISTS native_mentor_quest_facts(
        operation TEXT NOT NULL,owner INTEGER NOT NULL,kind TEXT NOT NULL,fact_json TEXT NOT NULL,
        PRIMARY KEY(operation,owner,kind))''')
    raw=_json(dict(pair=fact,activity=activity))
    old=db.execute('SELECT fact_json FROM native_mentor_quest_facts WHERE operation=?AND owner=?AND kind=?',
                   (operation,owner,activity['kind'])).fetchone()
    if old is not None:
        if old!=(raw,):raise ValueError('Mentor task producer changed')
        return []
    changed=[]
    for row in rows:
        qid=row['id']
        if rules.teacher(qid)!=(owner==fact['teacher']):continue
        quest=rules.catalog()['quests'][str(qid)];condition=quest['QuestCondition']
        level=relations.character(db,uid=owner)['level']if rules.teacher(qid)else fact['student_level']
        if level<condition['m_iLevel']or condition['m_iLimitLevel']>0 and level>condition['m_iLimitLevel']:continue
        counts=dict(row['objectives'])
        for sid in counts:
            sub=rules.catalog()['subquests'][str(sid)]
            counts[sid]=min(rules.target(sub),counts[sid]+rules.increment(qid,sub,fact,activity))
        if counts!=row['objectives']:
            if db.execute('UPDATE character_quests SET objectives=?WHERE owner=?AND quest=?AND generation=?',
                    (_json(counts),owner,qid,row['generation'])).rowcount!=1:raise ValueError('Mentor task generation changed')
            changed.append(dict(row,objectives=counts))
    db.execute('INSERT INTO native_mentor_quest_facts VALUES(?,?,?,?)',(operation,owner,activity['kind'],raw))
    from els_server.protocol.quest_messages import progress
    from els_server.protocol.protocol_codec import encode_event
    answer=[progress(changed)]if changed else []
    for event in answer:encode_event(event)
    if guard(db)is not True:raise ValueError('Mentor task late actor changed')
    return answer
