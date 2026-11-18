"""Prospective title progress in the original event/reward transaction."""
from functools import lru_cache
from els_server.storage import titles
from els_server.protocol import title_messages as wire

TABLE='title_count_progress'

@lru_cache(maxsize=1)
def rules():
    from els_server.domain.title_count_rules import rules as clears
    from els_server.domain.title_kill_rules import rules as kills
    from els_server.domain.title_condition_rules import rules as extended
    result=(*clears(),*kills(),*extended())
    if len({r.mission for r in result})!=len(result):raise ValueError('Duplicate admitted title mission')
    return result


def counts(db,account,uid=None):
    result={}
    for table,column,subject in ((TABLE,'account_id',account),('title_character_count_progress','owner',uid)):
        if subject is None or not titles.exists(db,table):continue
        for mission,submission,count in db.execute(f'SELECT mission,submission,count FROM {table} WHERE {column}=?',(subject,)):
            if type(count)is not int or not 0<=count<=32767:raise ValueError('Invalid persisted title count')
            result[(mission,submission)]=count
    return result


def value(rule,objective,current,character=None,owned=()):
    if hasattr(objective,'condition') and character is not None:
        from els_server.domain.title_condition_rules import state_count
        fact=state_count(objective,character,owned)
        if fact is not None:return fact
    return min(objective.target,current.get((rule.mission,objective.submission),0))


def complete(rule,current,character=None,owned=()):
    ordinary=[o for o in rule.objectives if not getattr(o,'force',False)]
    alternatives=[o for o in rule.objectives if getattr(o,'force',False)]
    return (bool(ordinary) and all(value(rule,o,current,character,owned)>=o.target for o in ordinary)
        or any(value(rule,o,current,character,owned)>=o.target for o in alternatives))


def qualified(rule,character,current,all_rules,owned=()):
    if character['level']<rule.level:return False
    if getattr(rule,'unit_type',0) not in (0,character['unit_type']):return False
    if getattr(rule,'unit_class',0) not in (0,character['unit_class']):return False
    return all(p in owned or p in all_rules and complete(all_rules[p],current,character,owned) for p in rule.prerequisites)


def matches(objective,dungeon,seconds):
    return getattr(objective,'kind',8)!=2 and dungeon in objective.maps and (objective.max_seconds is None or seconds is not None and 0<seconds<=objective.max_seconds)


def commit(db,uid,dungeon,now,*,seconds=None,context=None):
    if not db.in_transaction:raise ValueError('Title counts require caller transaction')
    if seconds is not None and (type(seconds)is not int or not 0<=seconds<=2147483647):raise ValueError('Title clear elapsed seconds')
    if not all(titles.exists(db,t) for t in ('characters','character_owners')):return ()
    if not db.execute('SELECT 1 FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=?',(uid,)).fetchone():return ()
    event=dict(context or {},kind='clear',dungeon=dungeon,seconds=seconds)
    return advance(db,titles.character(db,uid),now,lambda o:matches(o,dungeon,seconds),event=event)


def _schema(db,account):
    if account:
        db.execute('CREATE TABLE IF NOT EXISTS title_count_progress (account_id INTEGER NOT NULL CHECK(account_id>0),mission INTEGER NOT NULL,submission INTEGER NOT NULL,count INTEGER NOT NULL CHECK(count>=0 AND count<=32767),PRIMARY KEY(account_id,mission,submission))')
    else:
        db.execute('CREATE TABLE IF NOT EXISTS title_character_count_progress (owner INTEGER NOT NULL,mission INTEGER NOT NULL,submission INTEGER NOT NULL,count INTEGER NOT NULL CHECK(count>=0 AND count<=32767),PRIMARY KEY(owner,mission,submission))')


def _weekly(db,rule,objective,character,now):
    limit=getattr(objective,'weekly',0)
    if not limit:return True
    from els_server.storage.raid_economy_state import week_at
    scope='account' if getattr(rule,'account',True) else 'character'
    subject=character['account_id'] if scope=='account' else character['uid']
    week=week_at(now)
    db.execute('CREATE TABLE IF NOT EXISTS title_weekly_counts (scope TEXT NOT NULL,subject INTEGER NOT NULL,mission INTEGER NOT NULL,submission INTEGER NOT NULL,week INTEGER NOT NULL,count INTEGER NOT NULL,PRIMARY KEY(scope,subject,mission,submission,week))')
    key=(scope,subject,rule.mission,objective.submission,week)
    row=db.execute('SELECT count FROM title_weekly_counts WHERE scope=? AND subject=? AND mission=? AND submission=? AND week=?',key).fetchone()
    if row and row[0]>=limit:return False
    db.execute('INSERT INTO title_weekly_counts VALUES (?,?,?,?,?,1) ON CONFLICT(scope,subject,mission,submission,week) DO UPDATE SET count=count+1',key)
    return True


def advance(db,character,now,predicate=None,*,event=None):
    if not db.in_transaction:raise ValueError('Title advance requires caller transaction')
    admitted=rules();by_id={r.mission:r for r in admitted}
    current=counts(db,character['account_id'],character['uid'])
    acquired={r['title'] for r in titles.owned(db,character,now)}
    from els_server.domain.title_condition_rules import matches as condition_matches
    def matches_event(o):
        if hasattr(o,'condition'):
            return event is not None and condition_matches(o,event)
        return predicate(o) if predicate is not None else False
    active=[]
    # Freeze eligibility before the event; discovering a title cannot reuse
    # that same kill/clear as its first obtain count.
    for rule in admitted:
        if (rule.title and rule.title in acquired) or not qualified(rule,character,current,by_id,acquired):continue
        if getattr(rule,'simultaneous',False) and not all(matches_event(o) for o in rule.objectives):continue
        objectives=tuple(o for o in rule.objectives if matches_event(o)
            and value(rule,o,current,character,acquired)<o.target)
        if objectives or rule.title and complete(rule,current,character,acquired):active.append((rule,objectives))
    if not active:return ()
    from els_server.domain.title_bonus_counts import rate,increment
    bonus=rate(db,character,now) if any(r.title for r,_ in active) else 0
    titles.schema(db);awarded=[]
    for rule,objectives in active:
        account=getattr(rule,'account',True)
        _schema(db,account)
        table=TABLE if account else 'title_character_count_progress'
        column='account_id' if account else 'owner'
        subject=character['account_id'] if account else character['uid']
        for objective in objectives:
            if not _weekly(db,rule,objective,character,now):continue
            key=(rule.mission,objective.submission)
            previous=current.get(key,0)
            extra=(rule.title and not getattr(objective,'ignore_bonus',False)
                and not getattr(objective,'weekly',0) and getattr(objective,'kind',8) in (2,5,6,7,8,17,18,19,31))
            step=increment(objective.target-previous,bonus) if extra else 1
            count=min(objective.target,previous+step)
            db.execute(f'INSERT INTO {table} VALUES (?,?,?,?) ON CONFLICT({column},mission,submission) DO UPDATE SET count=excluded.count',(subject,*key,count))
            current[key]=count
        if rule.title and complete(rule,current,character,acquired):
            scope,subject=titles.scope(character,rule.title)
            inserted=db.execute('INSERT OR IGNORE INTO title_ownership VALUES (?,?,?,?,?,?)',(scope,subject,rule.title,character['name'],now,0)).rowcount
            if inserted:awarded.append(rule.title)
    response=wire.initialization(titles.snapshot(db,character['uid'],now))
    if not isinstance(response.payload,bytes) or not 1<=len(response.payload)<=65536:raise ValueError('Title count response bounds')
    return tuple(awarded)


def opened(db,character,owned):
    acquired={r['title'] for r in owned};current=counts(db,character['account_id'],character['uid'])
    admitted=rules();by_id={r.mission:r for r in admitted};result=[]
    for rule in admitted:
        if not rule.title or rule.title in acquired or not qualified(rule,character,current,by_id,acquired):continue
        progress=[]
        for objective in rule.objectives:
            count=value(rule,objective,current,character,acquired)
            progress.append(dict(sub=objective.submission,count=count,done=count>=objective.target))
        result.append(dict(mission=rule.mission,flag=0,progress=progress))
    return result
