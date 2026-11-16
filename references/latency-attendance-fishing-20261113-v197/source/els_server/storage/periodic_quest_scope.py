"""Account quest ownership and period rollover in the original quest writer."""
import json
from els_server.storage import pet_battle_quest_scope as legacy
from els_server.domain import periodic_activities as rules

exists=legacy.exists
account=legacy.account
ACTIVE='periodic_active_quests_v1'
COMPLETED='periodic_completed_quests_v1'

def scoped(qid):return rules.contains(qid) or legacy.scoped(qid)

def _rows(db,uid,table,columns,quest_ids=None):
    ids=tuple(q for q in rules.catalog()['weekly_ids']+rules.catalog()['pass_ids']+rules.catalog()['ordinary_weekly_ids']
              if quest_ids is None or q in quest_ids)
    if not ids or not exists(db,table):return []
    rows=db.execute('SELECT '+columns+',q.quest,q.owner FROM '+table+' q JOIN character_owners o ON o.uid=q.owner '
        'WHERE o.account_id=? AND q.quest IN('+','.join('?'for _ in ids)+')', (account(db,uid),*ids))
    return [row[:-2]for row in rows if rules.account_scoped(row[-2])or row[-1]==uid]

def active_rows(db,uid,*,quest_ids=None):
    rows=legacy.active_rows(db,uid,quest_ids=quest_ids)
    rows+=_rows(db,uid,ACTIVE,'q.quest,q.accepted_at,q.generation,q.objectives',quest_ids)
    if len({r[0]for r in rows})!=len(rows):raise ValueError('Duplicate account periodic task carriers')
    return sorted(rows)

def completed_rows(db,uid):
    rows=legacy.completed_rows(db,uid)
    rows+=_rows(db,uid,COMPLETED,'q.quest,q.completed_at')
    if len({r[0]for r in rows})!=len(rows):raise ValueError('Duplicate account periodic completions')
    return sorted(rows)

def quest_owner(db,uid,qid):
    if not rules.contains(qid):return legacy.quest_owner(db,uid,qid)
    owners=[]
    for table in (ACTIVE,COMPLETED):
        owners+=_rows(db,uid,table,'q.owner',(qid,))
    if len(set(owners))>1:raise ValueError('Conflicting account periodic owner')
    return owners[0][0]if owners else uid


def quest_owners(db,uid,quest_ids):
    """Resolve one task projection from its caller's current SQL snapshot."""
    selected=frozenset(quest_ids)
    periodic=frozenset(q for q in selected if rules.contains(q))
    owners={q:set()for q in periodic}
    if periodic:
        for table in(ACTIVE,COMPLETED):
            for q,owner in _rows(db,uid,table,'q.quest,q.owner',periodic):
                owners[q].add(owner)
    if any(len(v)>1 for v in owners.values()):raise ValueError('Conflicting account periodic owner')
    return {q:(next(iter(owners[q]))if owners[q]else uid)if q in periodic else legacy.quest_owner(db,uid,q)
            for q in selected}

def _guard(db,uid,expected,guard):
    if not callable(guard):raise ValueError('Periodic task current actor required')
    getattr(guard,'periodic_guard',guard)(db)
    from els_server.storage.item_actor import require_active_character
    require_active_character(db,uid)
    account(db,uid,expected)

def ensure(db):
    if not db.in_transaction:raise ValueError('Periodic quest original writer required')
    # Older releases traverse the legacy tables with a closed quest catalog.
    # Store new IDs separately so the same save can open during recovery.
    db.execute(f'''CREATE TABLE IF NOT EXISTS {ACTIVE}(
        owner INTEGER NOT NULL REFERENCES characters(uid), quest INTEGER NOT NULL,
        accepted_at INTEGER NOT NULL, generation INTEGER NOT NULL, objectives TEXT NOT NULL,
        PRIMARY KEY(owner,quest))''')
    db.execute(f'''CREATE TABLE IF NOT EXISTS {COMPLETED}(
        owner INTEGER NOT NULL REFERENCES characters(uid), quest INTEGER NOT NULL,
        completed_at INTEGER NOT NULL, reward_json TEXT NOT NULL, PRIMARY KEY(owner,quest))''')
    db.execute('CREATE TABLE IF NOT EXISTS periodic_quest_history_v1(account INTEGER NOT NULL,scope_owner INTEGER NOT NULL,quest INTEGER NOT NULL,period INTEGER NOT NULL,kind TEXT NOT NULL,state_json TEXT NOT NULL,PRIMARY KEY(account,scope_owner,quest,period,kind))')
    db.execute('CREATE TABLE IF NOT EXISTS periodic_quest_operations_v1(operation TEXT PRIMARY KEY,account INTEGER NOT NULL,quest INTEGER NOT NULL,period INTEGER NOT NULL)')

def rollover(db,uid,now):
    ensure(db);owner_account=account(db,uid)
    for table,columns,kind in ((ACTIVE,'q.owner,q.quest,q.accepted_at,q.generation,q.objectives','active'),
                               (COMPLETED,'q.owner,q.quest,q.completed_at,q.reward_json','completed')):
        for row in _rows(db,uid,table,columns):
            owner,qid,at,*saved=row;q=rules.definition(qid)
            current=rules.period(now,q['m_eRepeatType']);old=rules.period(at,q['m_eRepeatType'])
            if old>current:raise ValueError('Periodic quest clock moved backwards')
            # Weekly mission unfinished progress survives Wednesday's reset.
            if rules.visible(qid,at,now,active=kind=='active'):continue
            db.execute('INSERT INTO periodic_quest_history_v1 VALUES(?,?,?,?,?,?)',
                       (owner_account,0 if rules.account_scoped(qid)else uid,qid,old,kind,json.dumps(row)))
            db.execute('DELETE FROM '+table+' WHERE owner=? AND quest=?',(owner,qid))

def before_action(db,uid,expected,kind,guard,*,qid):
    if not rules.contains(qid):return legacy.before_action(db,uid,expected,kind,guard,qid=qid)
    _guard(db,uid,expected,guard)

def prepare(store,db,qid,operation,kind,now):
    if not rules.contains(qid):return
    _guard(db,store.uid,store.account_id,store.account_source_guard)
    rollover(db,store.uid,now)
    q=rules.definition(qid)
    from els_server.storage.seal_quests import load_character
    tier=1
    if rules.pass_task(qid):
        from els_server.storage.season_pass import state
        tier=state(db,store.account_id,q['m_eSeasonPassCategory'],now)['tier']
    rules.eligible(load_character(db,store.uid,store.account_id,identity_only=True),q,now,tier)
    current=rules.period(now,q['m_eRepeatType'])
    old=db.execute('SELECT account,quest,period FROM periodic_quest_operations_v1 WHERE operation=?',(operation,)).fetchone()
    if old is not None and old!=(store.account_id,qid,current):raise ValueError('Periodic operation belongs to another reset')
    if rules.weekly(qid):
        active=[r for r in active_rows(db,store.uid)if rules.weekly(r[0])]
        done=[r for r in completed_rows(db,store.uid)if rules.weekly(r[0])]
        if kind=='accept'and qid not in {r[0]for r in active+done}and len(active)+len(done)>=4:
            raise ValueError('Weekly account mission limit reached')
        if kind=='abandon':
            row=next((r for r in active if r[0]==qid),None)
            if row:
                from els_server.domain.seal_quests import quest_catalog,target
                counts=json.loads(row[3])
                if all(counts[str(s['m_iID'])]>=target(s)for s in quest_catalog().objectives(qid)):
                    raise ValueError('Ready weekly mission cannot be abandoned')
    elif rules.pass_task(qid)and kind=='abandon':raise ValueError('Pass task cannot be abandoned')
    db.execute('INSERT OR IGNORE INTO periodic_quest_operations_v1 VALUES(?,?,?,?)',(operation,store.account_id,qid,current))

def insert_active(db,uid,qid,now,generation,raw):
    if not rules.contains(qid):return legacy.insert_active(db,uid,qid,now,generation,raw)
    if _rows(db,uid,ACTIVE,'q.owner',(qid,)) or _rows(db,uid,COMPLETED,'q.owner',(qid,)):
        raise ValueError('Account periodic task already active/completed')
    db.execute(f'INSERT INTO {ACTIVE} VALUES(?,?,?,?,?)',(uid,qid,now,generation,raw))

def delete_active(db,uid,qid):
    table=ACTIVE if rules.contains(qid) else 'character_quests'
    db.execute(f'DELETE FROM {table} WHERE owner=? AND quest=?',(quest_owner(db,uid,qid),qid))

def update_objectives(db,uid,qid,counts):
    table=ACTIVE if rules.contains(qid) else 'character_quests'
    return db.execute(f'UPDATE {table} SET objectives=? WHERE owner=? AND quest=?',
                      (json.dumps(counts,sort_keys=True),quest_owner(db,uid,qid),qid)).rowcount

def insert_completed(db,uid,qid,now,reward):
    if not rules.contains(qid):return legacy.insert_completed(db,uid,qid,now,reward)
    owner=quest_owner(db,uid,qid)
    db.execute(f'INSERT INTO {COMPLETED} VALUES(?,?,?,?)',(owner,qid,now,json.dumps(dict(reward,account_reward_recipient=uid),sort_keys=True)))
    if rules.pass_task(qid):
        from els_server.storage.season_pass import credit
        credit(db,account(db,uid),rules.definition(qid),now)

def reward_row(db,uid,qid):
    if not rules.contains(qid):return legacy.reward_row(db,uid,qid)
    row=db.execute(f'SELECT reward_json FROM {COMPLETED} WHERE owner=? AND quest=?',(quest_owner(db,uid,qid),qid)).fetchone()
    return None if row and json.loads(row[0]).get('account_reward_recipient')!=uid else row

def progress_allowed(db,uid,expected,event_id,event,proof,guard,*,qid):
    if not rules.contains(qid):return legacy.progress_allowed(db,uid,expected,event_id,event,proof,guard,qid=qid)
    _guard(db,uid,expected,guard)
    return True

def grant_weekly(store,db,qid,operation,now):
    from els_server.domain import periodic_reward_items as rewards
    from els_server.domain.raid_reward_items import _issue_source
    from els_server.storage.inventory_state import grant_items
    plan=rewards.weekly_plan(qid)
    def guard(current):
        _guard(current,store.uid,store.account_id,store.account_source_guard)
        saved=current.execute('SELECT account,quest,period FROM periodic_quest_operations_v1 WHERE operation=?',(operation,)).fetchone()
        if saved!=(store.account_id,qid,rules.period(now,3)):raise ValueError('Ordinary weekly reward operation changed')
        return True
    source=_issue_source(db,store.uid,'weekly:'+operation,'ordinary',dict(policy=rewards.WEEKLY_POLICY,
        owner=store.uid,account=store.account_id,quest=qid,readers_sha256=rewards.DATA_SHA),plan,guard)
    return grant_items(db,plan,store.uid,raid_reward_source=source)

