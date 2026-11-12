"""Persist current account pass XP; all changes use the existing quest writer."""
import json
from els_server.domain import periodic_activities as rules

def ensure(db):
    if not db.in_transaction:raise ValueError('Pass original writer required')
    db.execute('''CREATE TABLE IF NOT EXISTS season_pass_accounts_v1(
        account INTEGER NOT NULL,category INTEGER NOT NULL,season INTEGER NOT NULL,
        tier INTEGER NOT NULL CHECK(tier IN(1,2)),experience INTEGER NOT NULL CHECK(experience>=0),
        day INTEGER NOT NULL,daily_exp INTEGER NOT NULL CHECK(daily_exp>=0),
        week INTEGER NOT NULL,weekly_exp INTEGER NOT NULL CHECK(weekly_exp>=0),
        attendance INTEGER NOT NULL,claimed_json TEXT NOT NULL,
        PRIMARY KEY(account,category,season))''')

def state(db,account,category,now):
    window=rules.active_season(now)
    if window is None:raise ValueError('Pass season is closed')
    begin,end,season=window
    if type(account)is not int or account<=0 or str(category)not in rules.catalog()['passes']:
        raise ValueError('Current pass account/category')
    day=rules.period(now,1);week=rules.period(now,3)
    row=None
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='season_pass_accounts_v1' AND type='table'").fetchone():
        row=db.execute('SELECT tier,experience,day,daily_exp,week,weekly_exp,attendance,claimed_json FROM season_pass_accounts_v1 WHERE account=? AND category=? AND season=?',(account,category,season)).fetchone()
    if row is None:row=(1,0,day,0,week,0,0,'[]')
    if row[2]>day or row[4]>week:raise ValueError('Pass clock moved before saved reset')
    return dict(account=account,category=category,season=season,tier=row[0],experience=row[1],
                day=day,daily_exp=row[3]if row[2]==day else 0,
                week=week,weekly_exp=row[5]if row[4]==week else 0,
                attendance=row[6],claimed=json.loads(row[7]),begin=begin,end=end,now=now)

def save(db,value):
    ensure(db)
    db.execute('''INSERT INTO season_pass_accounts_v1 VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(account,category,season)DO UPDATE SET tier=excluded.tier,
        experience=excluded.experience,day=excluded.day,daily_exp=excluded.daily_exp,
        week=excluded.week,weekly_exp=excluded.weekly_exp,attendance=excluded.attendance,
        claimed_json=excluded.claimed_json''',tuple(value[k]for k in
        ('account','category','season','tier','experience','day','daily_exp','week','weekly_exp','attendance'))+
        (json.dumps(value['claimed']),))

def credit(db,account,quest,now):
    category=quest['m_eSeasonPassCategory'];config=rules.catalog()['passes'][str(category)]
    value=state(db,account,category,now);amount=quest['Reward']['m_iSeasonPassEXP']
    repeat=quest['m_eRepeatType']
    if repeat==1:amount=min(amount,max(0,config['DailyMaxEXP']-value['daily_exp']))
    if repeat==3:amount=min(amount,max(0,config['WeeklyMaxExp']-value['weekly_exp']))
    amount=min(amount,max(0,config['TotalExp']-value['experience']))
    value['experience']+=amount
    if repeat==1:value['daily_exp']+=amount
    if repeat==3:value['weekly_exp']+=amount
    save(db,value)

def restore(store,db,now,*,character=None):
    """Restore unclaimed tasks for the account's current entitlement."""
    from els_server.storage import periodic_quest_scope as scope
    from els_server.storage.seal_quests import ensure as ensure_quests,load_character
    ensure_quests(db);scope._guard(db,store.uid,store.account_id,store.account_source_guard)
    scope.rollover(db,store.uid,now)
    if rules.active_season(now)is None:return []
    if character is None:
        character=load_character(db,store.uid,store.account_id,identity_only=True)
    active={qid:raw for qid,_,_,raw in scope.active_rows(db,store.uid)}
    done={qid for qid,_ in scope.completed_rows(db,store.uid)}
    values={int(category):state(db,store.account_id,int(category),now)
            for category in rules.catalog()['passes']}
    added=[]
    for qid in rules.catalog()['pass_ids']:
        if qid in done:continue
        q=rules.definition(qid);category=q['m_eSeasonPassCategory'];value=values[category]
        if character['level']<q['m_iPlayLevel']or 'SPT_CASH'in q.get('FLAGS','')and value['tier']!=2:continue
        if category in (3,4) and q['m_eRepeatType']==1 and value['attendance']>=value['day']:
            # The original shared check-in stamped locked tracks. An uncredited
            # daily attendance objective identifies the stale stamp after activation.
            objectives=json.loads(active[qid]) if qid in active else {}
            subs=rules.catalog()['subquests']
            if any(sub and subs[str(sub)]['m_eClearType']==88 and not objectives.get(str(sub))
                   for sub in q['m_vecSubQuest'].values()):
                value['attendance']=0
        if qid in active:continue
        rules.eligible(character,q,now,value['tier'])
        counts={s:0 for s in q['m_vecSubQuest'].values()if s}
        scope.insert_active(db,store.uid,qid,now,now,json.dumps(counts,sort_keys=True))
        added.append(dict(id=qid,owner=store.uid,accepted_at=now,generation=now,objectives=counts))
    for value in values.values():
        save(db,value)
    scope._guard(db,store.uid,store.account_id,store.account_source_guard)
    return added

def activate_premium(store,db,category,operation,digest,now):
    from els_server.domain.season_pass_shop import PRICE, on_sale
    from els_server.storage import periodic_quest_scope as scope
    from els_server.storage.npc_trade import balances,charge
    from els_server.storage.seal_quests import load_character

    scope._guard(db,store.uid,store.account_id,store.account_source_guard)
    value=state(db,store.account_id,category,now)
    db.execute('''CREATE TABLE IF NOT EXISTS season_pass_purchases_v1(
        operation TEXT PRIMARY KEY,account INTEGER NOT NULL,owner INTEGER NOT NULL,
        category INTEGER NOT NULL,season INTEGER NOT NULL,request_sha256 TEXT NOT NULL)''')
    identity=(store.account_id,store.uid,category,value['season'],digest)
    old=db.execute('SELECT account,owner,category,season,request_sha256 FROM season_pass_purchases_v1 WHERE operation=?',
                   (operation,)).fetchone()
    wallet=balances(db,store.uid)
    if old is not None:
        if old!=identity:raise ValueError('Conflicting pass purchase retry')
        return wallet['ed'],value,[]
    character=load_character(db,store.uid,store.account_id,identity_only=True)
    if not on_sale(category,now) or value['tier']!=1 or character['level']<rules.PASS_MIN_LEVEL:
        raise ValueError('Magmelia Express activation unavailable for this account')
    ed=charge(db,store.uid,wallet,PRICE)
    value['tier']=2
    save(db,value)
    added=restore(store,db,now,character=character)
    db.execute('INSERT INTO season_pass_purchases_v1 VALUES(?,?,?,?,?,?)',(operation,*identity))
    return ed,state(db,store.account_id,category,now),added

def attendance(store,db,category,now):
    """One account check-in advances native attendance objectives together."""
    from els_server.storage import periodic_quest_scope as scope
    from els_server.domain.seal_quests import quest_catalog,target
    from els_server.storage.seal_quests import load_character
    character=load_character(db,store.uid,store.account_id,identity_only=True)
    if character['level']<rules.PASS_MIN_LEVEL:
        raise ValueError('Pass attendance level requirement')
    restore(store,db,now,character=character)
    state(db,store.account_id,category,now)
    changed=[];checked_in={}
    for active in scope.active_rows(db,store.uid):
        qid,at,generation,raw=active
        if not rules.pass_task(qid):continue
        q=rules.definition(qid);value=state(db,store.account_id,q['m_eSeasonPassCategory'],now)
        if value['attendance']>=value['day']:continue
        counts={int(k):v for k,v in json.loads(raw).items()};updated=dict(counts)
        for sub in quest_catalog().objectives(qid):
            if sub['m_eClearType']==88:updated[sub['m_iID']]=min(target(sub),counts[sub['m_iID']]+1)
        if updated!=counts:
            scope.update_objectives(db,store.uid,qid,updated)
            checked_in[value['category']]=value
            changed.append(dict(id=qid,owner=store.uid,projection_owner=store.uid,
                                accepted_at=at,generation=generation,objectives=updated))
    for value in checked_in.values():
        value['attendance']=now;save(db,value)
    scope._guard(db,store.uid,store.account_id,store.account_source_guard)
    return changed

def advance(store,db,kind,value,now):
    """Consume a newly committed source inside that source's original writer."""
    from els_server.storage import periodic_quest_scope as scope
    from els_server.domain.seal_quests import quest_catalog,target,sequence
    if not scope.exists(db,scope.ACTIVE)or not any(rules.pass_task(r[0])for r in scope.active_rows(db,store.uid)):return []
    restore(store,db,now);changed=[]
    for qid,at,generation,raw in scope.active_rows(db,store.uid):
        if not rules.pass_task(qid):continue
        counts={int(k):v for k,v in json.loads(raw).items()};updated=dict(counts)
        for sub in quest_catalog().objectives(qid):
            condition=sub['m_ClearCondition'];clear=sub['m_eClearType']
            matches=(kind=='repair'and clear==87 or kind=='talk'and clear==1 and condition['m_eTalkNPCID']==value
                     or kind=='quest'and clear==89 and value in sequence(condition['m_eQuestID']))
            if matches:updated[sub['m_iID']]=min(target(sub),counts[sub['m_iID']]+1)
        if updated!=counts:
            scope.update_objectives(db,store.uid,qid,updated)
            changed.append(dict(id=qid,owner=store.uid,projection_owner=store.uid,
                                accepted_at=at,generation=generation,objectives=updated))
    scope._guard(db,store.uid,store.account_id,store.account_source_guard)
    return changed

def claim(store,db,category,claims,operation,digest,now,*,choice=None):
    from els_server.storage import periodic_quest_scope as scope
    from els_server.domain import periodic_reward_items as rewards
    from els_server.storage.inventory_state import grant_items
    from els_server.storage.seal_quests import load_character
    scope._guard(db,store.uid,store.account_id,store.account_source_guard)
    ensure(db);value=state(db,store.account_id,category,now)
    character=load_character(db,store.uid,store.account_id,identity_only=True)
    if character['level']<rules.PASS_MIN_LEVEL:raise ValueError('Pass reward level requirement')
    configured={(r['1'],r['2']):r for r in rules.catalog()['passes'][str(category)]['Reward'].values()}
    for pair in claims:
        row=configured.get(pair)
        if row is None or pair[0]>value['tier']or value['experience']<row['3']:
            raise ValueError('Pass reward is not earned')
    chip=rewards.chip_reward(category)
    chip_pair=(chip['PassType'],chip['Step']) if chip else None
    if chip_pair in claims:
        if (choice is None or choice[:2]!=chip_pair or choice[3]!=chip['DemeritSocketID']
            or choice[2] not in chip['SocketIDList'].values()):
            raise ValueError('Pass chip requires a configured effect choice')
    elif choice is not None:
        raise ValueError('Pass effect choice without its reward')
    db.execute('''CREATE TABLE IF NOT EXISTS season_pass_claims_v1(
        operation TEXT PRIMARY KEY,account INTEGER NOT NULL,owner INTEGER NOT NULL,
        category INTEGER NOT NULL,season INTEGER NOT NULL,request_sha256 TEXT NOT NULL,
        claims_json TEXT NOT NULL,items_json TEXT NOT NULL)''')
    identity=(store.account_id,store.uid,category,value['season'],digest)
    old=db.execute('SELECT account,owner,category,season,request_sha256 FROM season_pass_claims_v1 WHERE operation=?',(operation,)).fetchone()
    if old is not None:
        if old!=identity:raise ValueError('Conflicting pass reward operation')
        return [],[],value
    claimed={tuple(pair)for pair in value['claimed']};selected=tuple(pair for pair in claims if pair not in claimed)
    plan=rewards.plan(category,selected)
    db.execute('INSERT INTO season_pass_claims_v1 VALUES(?,?,?,?,?,?,?,?)',
               (operation,*identity,json.dumps(claims), '[]'))
    value['claimed']=[list(pair)for pair in sorted(claimed|set(selected))];save(db,value)
    if not plan:return [],[],value
    def guard(current):
        scope._guard(current,store.uid,store.account_id,store.account_source_guard)
        saved=state(current,store.account_id,category,now)
        if saved!=value:raise ValueError('Pass reward state changed during original writer')
        row=current.execute('SELECT account,owner,category,season,request_sha256 FROM season_pass_claims_v1 WHERE operation=?',(operation,)).fetchone()
        if row!=identity:raise ValueError('Pass claim receipt authority changed')
        return True
    from els_server.domain.raid_reward_items import _issue_source
    policy=rewards.PREMIUM_POLICY if any(track==2 for track,_ in selected) else rewards.POLICY
    source=_issue_source(db,store.uid,operation,'ordinary',dict(policy=policy,
        owner=store.uid,account=store.account_id,category=category,season=value['season'],
        claims=selected,readers_sha256=rewards.DATA_SHA),plan,guard)
    chip_options={'1':list(choice[2:])} if chip_pair in selected else None
    items=grant_items(db,plan,store.uid,raid_reward_source=source,chip_options=chip_options)
    if chip_options:
        from els_server.domain.equipment_chip_rules import PASS_CHIP,catalog as chip_catalog
        from els_server.storage.equipment_chip import replace
        item=next(i for i in items if i['template']==PASS_CHIP)
        success=chip['SuccessCount']
        # A completed chip cannot roll again until reset. Keep a valid stored
        # probability byte under the shared chip reader.
        tuning=[success+chip['FailCount'],success,chip_catalog()['minimum_probability'],0]
        replace(db,store.uid,item['uid'],[0,0,0,0],tuning)
        item['chip_tuning']=tuning
    db.execute('UPDATE season_pass_claims_v1 SET items_json=?WHERE operation=?',(json.dumps(items,sort_keys=True),operation))
    guard(db)
    return items,plan,value

