"""Prospective account title counts inside the caller's reward receipt.

The reward transaction supplies exactly one authenticated clear and guards retry.
Discovery completion unlocks subsequent clears; it is never a title ownership row.
Old boolean Ruben progress, existing player data and title effects are untouched.
"""
from els_server.storage import titles
from els_server.domain.title_count_rules import rules as clear_rules

def rules():
    from els_server.domain.title_kill_rules import rules as kill_rules
    return (*clear_rules(),*kill_rules())
from els_server.protocol import title_messages as wire

TABLE='title_count_progress'

def counts(db,account):
    if not titles.exists(db,TABLE):return {}
    rows=db.execute('SELECT mission,submission,count FROM title_count_progress WHERE account_id=?',(account,))
    result={}
    for mission,submission,count in rows:
        if type(count) is not int or not 0<=count<=32767:raise ValueError('Invalid persisted title count')
        result[(mission,submission)]=count
    return result

def qualified(rule,character,current,all_rules):
    if character['level']<rule.level:return False
    return all(complete(all_rules[p],current) for p in rule.prerequisites)

def complete(rule,current):
    return all(current.get((rule.mission,o.submission),0)>=o.target for o in rule.objectives)

def matches(objective,dungeon,seconds):
    return getattr(objective,'kind',8)!=2 and dungeon in objective.maps and (objective.max_seconds is None or seconds is not None and 0<seconds<=objective.max_seconds)

def commit(db,uid,dungeon,now,*,seconds=None):
    if not db.in_transaction:raise ValueError('Title counts require caller transaction')
    # RewardState and DungeonClock allow zero for an unrecorded/subsecond
    # clear. Ordinary objectives still count; timed objectives require a
    # positive measured value and cannot gain credit from unknown zero time.
    if seconds is not None and (type(seconds) is not int or not 0<=seconds<=2147483647):raise ValueError('Title clear elapsed seconds')
    # The public reward caller already validates its clear and identity. Preserve
    # protocol-only fixtures lacking authenticated characters without new tables.
    if not all(titles.exists(db,t) for t in ('characters','character_owners')):return ()
    if not db.execute('SELECT 1 FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=?',(uid,)).fetchone():return ()
    character=titles.character(db,uid);account=character['account_id']
    return advance(db,character,now,lambda o:matches(o,dungeon,seconds))

def advance(db,character,now,predicate):
    """Apply one server-observed event; caller owns its atomic receipt."""
    if not db.in_transaction:raise ValueError('Title advance requires caller transaction')
    account=character['account_id'];uid=character['uid']
    admitted=rules();by_id={r.mission:r for r in admitted};current=counts(db,account)
    acquired={r['title'] for r in titles.owned(db,character,now)}
    # Evaluate eligibility from state BEFORE this event. A discovery clear may
    # unlock a mission but cannot also be reused as its first obtain clear.
    active=[(r,tuple(o for o in r.objectives if predicate(o) and current.get((r.mission,o.submission),0)<o.target))
            for r in admitted if qualified(r,character,current,by_id) and (not r.title or r.title not in acquired)]
    active=[(r,objectives) for r,objectives in active if objectives]
    if not active:return ()
    from els_server.domain.title_bonus_counts import rate,increment
    bonus=rate(db,character,now) if any(r.title for r,objectives in active) else 0
    titles.schema(db)
    db.execute('CREATE TABLE IF NOT EXISTS title_count_progress (account_id INTEGER NOT NULL CHECK(account_id>0),mission INTEGER NOT NULL,submission INTEGER NOT NULL,count INTEGER NOT NULL CHECK(count>=0 AND count<=32767),PRIMARY KEY(account_id,mission,submission))')
    awarded=[]
    for r,objectives in active:
        for objective in objectives:
            key=(r.mission,objective.submission)
            previous=current.get(key,0)
            # Only an already-open obtain objective can receive one extra
            # count. The caller's committed receipt prevents another draw.
            step=increment(objective.target-previous,bonus) if r.title else 1
            value=min(objective.target,previous+step)
            db.execute('INSERT INTO title_count_progress VALUES (?,?,?,?) ON CONFLICT(account_id,mission,submission) DO UPDATE SET count=excluded.count',(account,*key,value))
            current[key]=value
        if r.title and complete(r,current):
            db.execute('INSERT INTO title_ownership VALUES (?,?,?,?,?,?)',('account',account,r.title,character['name'],now,0))
            awarded.append(r.title)
    # Validate the native DTO for partial counters and newly discovered missions
    # inside the same transaction, before economic or title state commits.
    event=wire.initialization(titles.snapshot(db,uid,now))
    if not isinstance(event.payload,bytes) or not 1<=len(event.payload)<=65536:raise ValueError('Title count response bounds')
    return tuple(awarded)

def opened(db,character,owned):
    acquired={r['title'] for r in owned};current=counts(db,character['account_id'])
    admitted=rules();by_id={r.mission:r for r in admitted};result=[]
    for r in admitted:
        if not r.title or r.title in acquired or not qualified(r,character,current,by_id):continue
        progress=[]
        for objective in r.objectives:
            count=min(objective.target,current.get((r.mission,objective.submission),0))
            progress.append(dict(sub=objective.submission,count=count,done=count>=objective.target))
        result.append(dict(mission=r.mission,flag=0,progress=progress))
    return result
