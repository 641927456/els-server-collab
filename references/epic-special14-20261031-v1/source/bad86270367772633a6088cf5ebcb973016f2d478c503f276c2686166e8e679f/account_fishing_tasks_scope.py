"""Canonical account followups; retain the installed fishing table unchanged."""
import hashlib,json,struct
from els_server.storage import account_fishing25600_scope as legacy
QUEST=legacy.QUEST
PET_IDS=frozenset((25610,25611,25612))
IDS=frozenset((25601,25602))|PET_IDS
MUTATIONS_ENABLED=True
exists=legacy.exists
account=legacy.account


def scoped(qid):return qid in IDS or legacy.scoped(qid)


def _table(qid):
    return 'account_expedition_bindings' if qid in PET_IDS else 'account_fishing_followup_bindings'


def _binding(db,uid,qid):
    if not exists(db,_table(qid)):return None
    return db.execute('SELECT owner,accepted_action,source_floor FROM '+_table(qid)+' WHERE account=? AND quest=?',(account(db,uid),qid)).fetchone()


def _carriers(db,uid,qid):
    result=[]
    for kind,table in (('active','character_quests'),('completed','completed_quests')):
        if exists(db,table):result.extend((kind,r[0])for r in db.execute('SELECT q.owner FROM '+table+' q JOIN character_owners o ON o.uid=q.owner WHERE o.account_id=? AND q.quest=?',(account(db,uid),qid)))
    return result


def _integrity(db,uid,qid):
    b=_binding(db,uid,qid);rows=_carriers(db,uid,qid)
    if b is None:
        if rows:raise ValueError('Unbound fishing followup history requires review')
        return None
    if account(db,b[0])!=account(db,uid)or len(rows)>1 or any(owner!=b[0]for kind,owner in rows):raise ValueError('Conflicting fishing followup history')
    from els_server.protocol.quest_messages import request
    digest=hashlib.sha256(json.dumps([b[0],'accept',request(0xee,struct.pack('>ii',qid,10025))],sort_keys=True).encode()).hexdigest()
    if db.execute('SELECT owner,kind,request_hash FROM quest_actions WHERE rowid=?',(b[1],)).fetchone()!=(b[0],'accept',digest):raise ValueError('Fishing original EE provenance')
    if rows and rows[0][0]=='active' and db.execute('SELECT generation FROM character_quests WHERE owner=? AND quest=?',(b[0],qid)).fetchone()!=(b[1],):raise ValueError('Fishing active generation retired')
    return b


def _view(db,uid,qid):
    rows=_carriers(db,uid,qid);b=_binding(db,uid,qid)
    if len(rows)!=1:return None
    if b is None:return uid if rows[0][1]==uid else None
    return b[0]if rows[0][1]==b[0]and account(db,b[0])==account(db,uid)else None


def quest_owner(db,uid,qid):
    if qid not in IDS:return legacy.quest_owner(db,uid,qid)
    b=_binding(db,uid,qid);return b[0]if b else uid


def active_rows(db,uid):
    rows=[r for r in legacy.active_rows(db,uid)if r[0]not in IDS]
    for qid in IDS:
        owner=_view(db,uid,qid)
        if owner is not None:rows.extend(db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=?',(owner,qid)))
    return sorted(rows)


def completed_rows(db,uid):
    rows=[r for r in legacy.completed_rows(db,uid)if r[0]not in IDS]
    for qid in IDS:
        owner=_view(db,uid,qid)
        if owner is not None:rows.extend(db.execute('SELECT quest,completed_at FROM completed_quests WHERE owner=? AND quest=?',(owner,qid)))
    return sorted(rows)


def _actor(db,uid,expected,guard):
    if not db.in_transaction or not callable(guard):raise ValueError('Fishing quest current SQL guard required')
    guard(db)
    from els_server.storage.item_actor import require_active_character
    require_active_character(db,uid);a=account(db,uid,expected)
    if db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()!=(99,):raise ValueError('Fishing quest original99')
    return a


def before_action(db,uid,expected,kind,guard,*,qid=QUEST):
    if qid not in IDS:return legacy.before_action(db,uid,expected,kind,guard,qid=qid)
    if kind not in('accept','abandon','claim'):raise ValueError('Finite fishing quest action')
    a=_actor(db,uid,expected,guard);b=_integrity(db,uid,qid)
    done=b is not None and exists(db,'completed_quests')and db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(b[0],qid)).fetchone()is not None
    if not MUTATIONS_ENABLED and(kind=='accept'or kind=='claim'and not done):raise ValueError('New fishing quest delivery held')
    return a


def insert_active(db,uid,qid,now,generation,raw):
    if qid not in IDS:return legacy.insert_active(db,uid,qid,now,generation,raw)
    if not MUTATIONS_ENABLED or not db.in_transaction:raise ValueError('Fishing followup accept held')
    _integrity(db,uid,qid)
    if _carriers(db,uid,qid):raise ValueError('Fishing followup already active/completed')
    table='pet_expedition_receipts' if qid in PET_IDS else 'fishing_attempts'if qid==25601 else'inventory_action_receipts'
    floor=db.execute('SELECT COALESCE(MAX(rowid),0) FROM '+table).fetchone()[0]if exists(db,table)else 0
    db.execute('''CREATE TABLE IF NOT EXISTS '''+_table(qid)+'''(
       account INTEGER NOT NULL,quest INTEGER NOT NULL CHECK(quest IN('''+('25610,25611,25612' if qid in PET_IDS else '25601,25602')+''')), 
       owner INTEGER NOT NULL REFERENCES characters(uid),accepted_action INTEGER NOT NULL,
       source_floor INTEGER NOT NULL CHECK(source_floor>=0),PRIMARY KEY(account,quest))''')
    db.execute('INSERT INTO '+_table(qid)+' VALUES(?,?,?,?,?) ON CONFLICT(account,quest) DO UPDATE SET owner=excluded.owner,accepted_action=excluded.accepted_action,source_floor=excluded.source_floor',(account(db,uid),qid,uid,generation,floor))
    db.execute('INSERT INTO character_quests VALUES(?,?,?,?,?)',(uid,qid,now,generation,raw))


def insert_completed(db,uid,qid,now,reward):
    if qid not in IDS:return legacy.insert_completed(db,uid,qid,now,reward)
    if not MUTATIONS_ENABLED:raise ValueError('Fishing unfinished reward held')
    b=_integrity(db,uid,qid)
    if b is None:raise ValueError('Fishing followup binding required')
    db.execute('INSERT INTO completed_quests VALUES(?,?,?,?)',(b[0],qid,now,json.dumps(dict(reward,account_reward_recipient=uid),sort_keys=True)))


def reward_row(db,uid,qid):
    if qid not in IDS:return legacy.reward_row(db,uid,qid)
    row=db.execute('SELECT reward_json FROM completed_quests WHERE owner=? AND quest=?',(quest_owner(db,uid,qid),qid)).fetchone()
    return None if row is not None and json.loads(row[0]).get('account_reward_recipient')!=uid else row


def progress_allowed(db,uid,expected,event_id,event,proof,guard,*,qid=QUEST):
    if qid in IDS:return False
    return legacy.progress_allowed(db,uid,expected,event_id,event,proof,guard,qid=qid)


def _record(db,uid,expected,qid,operation,source,guard):
    from els_server.protocol.quest_messages import progress
    from els_server.protocol.protocol_codec import encode_event
    if not MUTATIONS_ENABLED:return []
    b=_integrity(db,uid,qid)
    if b is None:return []
    active=db.execute('SELECT accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=?',(b[0],qid)).fetchone()
    if active is None:return []
    _actor(db,uid,expected,guard)
    if active[1]!=b[1]or source['rowid']<=b[2]:return []
    sub=150300 if qid in PET_IDS else 25602 if qid==25601 else 25603;limit=10 if qid==25601 else 1
    counts=json.loads(active[2]);value=counts.get(str(sub),0)
    if value>=limit:return []
    event_id='fishing-task:'+str(qid)+':'+operation
    raw=json.dumps(dict(quest=qid,source=source,account=expected,actor=uid,accepted_owner=b[0],generation=b[1]),sort_keys=True);digest=hashlib.sha256(raw.encode()).hexdigest()
    old=db.execute('SELECT proof_hash,event_json FROM quest_progress_events WHERE owner=? AND event_id=?',(uid,event_id)).fetchone()
    if old is not None:
        if old!=(digest,raw):raise ValueError('Fishing task source retry conflict')
        return []
    counts[str(sub)]=value+1
    if db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=? AND generation=?',(json.dumps(counts,sort_keys=True),b[0],qid,b[1])).rowcount!=1:raise ValueError('Fishing task generation changed')
    db.execute('INSERT INTO quest_progress_events VALUES(?,?,?,?)',(uid,event_id,digest,raw))
    row=dict(id=qid,owner=b[0],projection_owner=uid,accepted_at=active[0],generation=b[1],objectives={int(k):v for k,v in counts.items()})
    result=[progress([row])]
    for event in result:encode_event(event)
    _actor(db,uid,expected,guard);_integrity(db,uid,qid)
    if not MUTATIONS_ENABLED:raise ValueError('Fishing progress held before commit')
    return result


def record_attempt(db,uid,expected,operation,guard):
    if not exists(db,'fishing_attempts'):raise ValueError('Real fishing attempt receipt required')
    row=db.execute('SELECT rowid,account,owner,cycle,serial,source_json FROM fishing_attempts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[1:3]!=(expected,uid):raise ValueError('Fishing attempt actor source')
    return _record(db,uid,expected,25601,operation,dict(rowid=row[0],cycle=row[3],serial=row[4],source_sha256=hashlib.sha256(row[5].encode()).hexdigest()),guard)


def record_exchange(db,uid,expected,operation,payload,guard):
    if not exists(db,'inventory_action_receipts'):raise ValueError('Real fishing exchange receipt required')
    from els_server.protocol.fish_exchange_messages import request
    from els_server.domain.fish_exchange_rules import recipe
    from els_server.storage.inventory_actions import _identity
    r=request(payload);recipe(r)
    if r.source not in(135933,135934,135935,135936,135937):raise ValueError('Original fishing source fish')
    _,digest=_identity(uid,0x223,b'House40256:'+payload,operation)
    row=db.execute('SELECT rowid,owner,kind,request_hash FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[1:]!=(uid,0x223,digest):raise ValueError('Fishing original exchange provenance')
    return _record(db,uid,expected,25602,operation,dict(rowid=row[0],fish=r.source,request_hash=digest),guard)


def record_expedition(db,uid,expected,operation,guard):
    # The completed expedition receipt is inserted by the same SQL writer.
    row=db.execute("SELECT rowid,owner,account,action,digest FROM pet_expedition_receipts WHERE operation=?",(operation,)).fetchone()
    if row is None or row[1:4]!=(uid,expected,'complete'):
        raise ValueError('Original completed expedition receipt required')
    events=[]
    for qid in sorted(PET_IDS):
        events.extend(_record(db,uid,expected,qid,operation,dict(rowid=row[0],digest=row[4]),guard))
    return events
