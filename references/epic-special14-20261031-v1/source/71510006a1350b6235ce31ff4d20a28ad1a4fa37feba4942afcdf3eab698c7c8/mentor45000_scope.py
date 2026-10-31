"""One account qualification task, advanced only by its original source writers."""
import hashlib,json,uuid
from els_server.storage import account_fishing_tasks_scope as legacy
from els_server.domain.mentor45000 import LIMITS

QUEST=45000
exists=legacy.exists;account=legacy.account
def scoped(qid):return qid==QUEST or legacy.scoped(qid)
def _binding(db,uid):
    if not exists(db,'account_mentor45000_bindings'):return None
    return db.execute('SELECT owner,accepted_action,reward_floor FROM account_mentor45000_bindings WHERE account=?',(account(db,uid),)).fetchone()
def _carriers(db,uid):
    out=[]
    for kind,table in(('active','character_quests'),('done','completed_quests')):
        if exists(db,table):out.extend((kind,r[0])for r in db.execute('SELECT q.owner FROM '+table+' q JOIN character_owners o ON o.uid=q.owner WHERE o.account_id=?AND q.quest=45000',(account(db,uid),)))
    return out
def _integrity(db,uid):
    b=_binding(db,uid);rows=_carriers(db,uid)
    if b is None:
        if rows:raise ValueError('Unbound mentor45000 history')
        return None
    if account(db,b[0])!=account(db,uid)or len(rows)>1 or any(r[1]!=b[0]for r in rows):raise ValueError('Mentor canonical account task conflict')
    action=db.execute('SELECT owner,kind,request_hash FROM quest_actions WHERE rowid=?',(b[1],)).fetchone()
    hashes={hashlib.sha256(json.dumps([b[0],'accept',dict(quest=45000,npc=npc)],sort_keys=True).encode()).hexdigest()for npc in(10142,10025)}
    if action is None or action[:2]!=(b[0],'accept')or action[2]not in hashes:raise ValueError('Mentor original acceptance action')
    if rows and rows[0][0]=='active'and db.execute('SELECT generation FROM character_quests WHERE owner=?AND quest=45000',(b[0],)).fetchone()!=(b[1],):raise ValueError('Mentor accepted generation changed')
    return b
def quest_owner(db,uid,qid):
    if qid!=QUEST:return legacy.quest_owner(db,uid,qid)
    b=_binding(db,uid);return b[0]if b else uid
def _view(db,uid):
    b=_binding(db,uid);rows=_carriers(db,uid)
    if len(rows)!=1:return None
    return rows[0][1]if b and rows[0][1]==b[0]or b is None and rows[0][1]==uid else None
def active_rows(db,uid):
    out=[r for r in legacy.active_rows(db,uid)if r[0]!=QUEST];owner=_view(db,uid)
    if owner is not None:out.extend(db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=?AND quest=45000',(owner,)))
    return sorted(out)
def completed_rows(db,uid):
    out=[r for r in legacy.completed_rows(db,uid)if r[0]!=QUEST];owner=_view(db,uid)
    if owner is not None:out.extend(db.execute('SELECT quest,completed_at FROM completed_quests WHERE owner=?AND quest=45000',(owner,)))
    return sorted(out)
def _actor(db,uid,expected,guard):
    if not db.in_transaction or not callable(guard):raise ValueError('Mentor current writer guard required')
    guarded=getattr(guard,'mentor_guard',guard);guarded(db)
    from els_server.storage.item_actor import require_active_character
    require_active_character(db,uid);a=account(db,uid,expected)
    if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):raise ValueError('Mentor original current level99')
    # Current server has no student relationship writer/store. This task
    # grants its native completed-quest qualification, not a relationship.
    return a
def before_action(db,uid,expected,kind,guard,*,qid=QUEST):
    if qid!=QUEST:return legacy.before_action(db,uid,expected,kind,guard,qid=qid)
    _actor(db,uid,expected,guard);_integrity(db,uid)
def insert_active(db,uid,qid,now,generation,raw):
    if qid!=QUEST:return legacy.insert_active(db,uid,qid,now,generation,raw)
    _integrity(db,uid)
    if _carriers(db,uid):raise ValueError('Mentor qualification already active/completed')
    floor=db.execute('SELECT COALESCE(MAX(rowid),0)FROM reward_receipts').fetchone()[0]if exists(db,'reward_receipts')else 0
    db.execute('''CREATE TABLE IF NOT EXISTS account_mentor45000_bindings(account INTEGER PRIMARY KEY,
        owner INTEGER NOT NULL REFERENCES characters(uid),accepted_action INTEGER NOT NULL,reward_floor INTEGER NOT NULL)''')
    db.execute('INSERT INTO account_mentor45000_bindings VALUES(?,?,?,?) ON CONFLICT(account) DO UPDATE SET owner=excluded.owner,accepted_action=excluded.accepted_action,reward_floor=excluded.reward_floor',(account(db,uid),uid,generation,floor))
    db.execute('''CREATE TABLE IF NOT EXISTS mentor45000_source_events(account INTEGER NOT NULL,generation INTEGER NOT NULL,
        operation TEXT NOT NULL,kind TEXT NOT NULL,actor INTEGER NOT NULL,source_hash TEXT NOT NULL,
        PRIMARY KEY(account,generation,operation,kind))''')
    db.execute('INSERT INTO character_quests VALUES(?,?,?,?,?)',(uid,qid,now,generation,raw))
def insert_completed(db,uid,qid,now,reward):
    if qid!=QUEST:return legacy.insert_completed(db,uid,qid,now,reward)
    b=_integrity(db,uid)
    if b is None:raise ValueError('Mentor acceptance required')
    db.execute('INSERT INTO completed_quests VALUES(?,?,?,?)',(b[0],qid,now,json.dumps(dict(reward,account_reward_recipient=uid),sort_keys=True)))
def reward_row(db,uid,qid):
    if qid!=QUEST:return legacy.reward_row(db,uid,qid)
    row=db.execute('SELECT reward_json FROM completed_quests WHERE owner=?AND quest=45000',(quest_owner(db,uid,qid),)).fetchone()
    return None if row and json.loads(row[0]).get('account_reward_recipient')!=uid else row
def capture(db,uid,expected,guard):
    if _binding(db,uid)is None:return None
    b=_integrity(db,uid)
    row=db.execute('SELECT generation,objectives FROM character_quests WHERE owner=?AND quest=45000',(b[0],)).fetchone()
    if row is None:return None
    if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):return None
    _actor(db,uid,expected,guard)
    if row[0]!=b[1]:raise ValueError('Mentor source acceptance changed')
    return b
def _source(db,uid,expected,operation,kind,source,guard):
    b=capture(db,uid,expected,guard)
    if b is None:return None
    raw=json.dumps(source,sort_keys=True,separators=(',',':'));digest=hashlib.sha256(raw.encode()).hexdigest()
    key=(expected,b[1],operation,kind)
    old=db.execute('SELECT actor,source_hash FROM mentor45000_source_events WHERE account=?AND generation=?AND operation=?AND kind=?',key).fetchone()
    if old:
        if old!=(uid,digest):raise ValueError('Mentor source replay changed')
        return None
    db.execute('INSERT INTO mentor45000_source_events VALUES(?,?,?,?,?,?)',(*key,uid,digest));return b
def advance(db,uid,expected,operation,kind,sub,source,guard):
    b=_source(db,uid,expected,operation,kind,source,guard)
    if b is None:return []
    raw=db.execute('SELECT objectives FROM character_quests WHERE owner=?AND quest=45000',(b[0],)).fetchone()[0];counts=json.loads(raw)
    if set(map(int,counts))!=set(LIMITS)or sub not in LIMITS:raise ValueError('Mentor exact nine objectives')
    counts[str(sub)]=min(LIMITS[sub],counts[str(sub)]+1)
    db.execute('UPDATE character_quests SET objectives=? WHERE owner=?AND quest=45000 AND generation=?',(json.dumps(counts,sort_keys=True),b[0],b[1]))
    from els_server.storage.seal_quests import _state
    from els_server.storage.inventory_state import load_items
    from els_server.protocol.quest_messages import progress
    from els_server.protocol.protocol_codec import encode_event
    row=next(r for r in _state(db,uid,load_items(db,uid))['active']if r['id']==QUEST)
    event=progress([row]);encode_event(event);_actor(db,uid,expected,guard);_integrity(db,uid)
    return [event]
def progress_allowed(db,uid,expected,event_id,event,proof,guard,*,qid=QUEST):
    if qid!=QUEST:return legacy.progress_allowed(db,uid,expected,event_id,event,proof,guard,qid=qid)
    b=capture(db,uid,expected,guard)
    if b is None:return False
    run=getattr(guard,'mentor_run',lambda:None)()
    if run is None or run.identity!=event['dungeon']:return False
    if event['kind']=='kill':
        if(event['dungeon'],event['npc'])!=(38300,1367):return False
        keys=[n['key']for n in run.current['npcs']if n['template']==1367 and n['active']and not n.get('ally')and n.get('team',1)!=0]
        if not any(event_id==f'{run.run_id}:{run.stage}:{run.part}:kill:{k}'and run.defeated.get(k)==proof for k in keys):return False
        source=dict(run=run.run_id,stage=run.stage,part=run.part,proof=hashlib.sha256(proof).hexdigest())
    elif event['kind']=='clear':
        from els_server.domain.mentor45000 import catalog
        from els_server.domain.seal_quests import objective_increment
        if not any(objective_increment(catalog()['subquests'][str(sid)],event,proof)for sid in(45050,45051)):return False
        if event_id!=run.run_id+':clear'or not exists(db,'reward_receipts'):return False
        reward_run=getattr(guard,'mentor_reward_run',lambda:None)()
        if not isinstance(reward_run,str):return False
        if reward_run!=run.run_id and reward_run!=str(uuid.uuid5(uuid.UUID(run.run_id),'reward:'+str(uid))):return False
        row=db.execute('SELECT rowid,proof_sha256,grant_json FROM reward_receipts WHERE run_id=?',(reward_run,)).fetchone()
        if row is None or row[0]<=b[2]:return False
        grant=json.loads(row[2]);pair=grant.get('dungeon_clear')
        if grant.get('owner',1001)!=uid or type(pair)is not list or len(pair)!=2 or pair[0]!=event['dungeon']:return False
        from els_server.storage.local_clear_rules import lookup_db
        saved=lookup_db(db,uid,reward_run)
        if saved is None or saved['assessment']['dungeon']!=pair[0]or saved['assessment']['seconds']!=pair[1]:return False
        source=dict(run=run.run_id,reward_run=reward_run,proof=row[1],grant=hashlib.sha256(row[2].encode()).hexdigest())
    else:return False
    return _source(db,uid,expected,event_id,event['kind'],source,guard)is not None

def paid(db,uid,expected,operation,old_level,new_level,result,guard):
    if(old_level,new_level,result)!=(5,6,1):return []
    row=db.execute('SELECT owner,kind,request_hash FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(uid,0x5ff):raise ValueError('Mentor real paid enhancement receipt')
    return advance(db,uid,expected,operation,'paid_enhancement',45054,dict(request=row[2],before=5,after=6),guard)

def warp(db,uid,expected,operation,guard):
    row=db.execute('SELECT proof_sha256,grant_json FROM reward_receipts WHERE run_id=?',(operation,)).fetchone()
    if row is None:raise ValueError('Mentor original Cobo receipt')
    grant=json.loads(row[1])
    if grant.get('kind')!='town_warp'or grant.get('owner')!=uid or grant.get('source')==grant.get('destination'):raise ValueError('Mentor real Cobo transition')
    return advance(db,uid,expected,operation,'town_warp',45053,dict(proof=row[0],grant=hashlib.sha256(row[1].encode()).hexdigest()),guard)

def official_win(db,uid,expected,rounds,result,guard):
    actor=next((m for m in result.members if m.account.uid==uid),None)
    if actor is None or result.killer is not actor or actor is result.leaver:return []
    if rounds.result(actor)is not result:raise ValueError('Mentor original sealed official result')
    return advance(db,uid,expected,result.seed,'official_pvp',45055,dict(seed=result.seed,room=result.room.identity,reason=result.reason,winner=uid),guard)
