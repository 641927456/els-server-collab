"""Original26770 only: one successful durable own-room admission is objective75."""
import json
WRITES_ENABLED=True
QUEST=26770
SUB={'m_iID':26770,'m_eClearType':75,'m_bAutomaticDescription':0,'m_ClearCondition':{}}

def target(sub):
    if sub!=SUB:raise ValueError('Unsupported housing objective source')
    return 1

def before_action(db,uid,account_id,kind,guard):
    from els_server.storage.item_actor import require_active_character
    if not callable(guard):raise ValueError('Housing quest current actor guard required')
    guard(db);require_active_character(db,uid)
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Housing quest owner')
    if not WRITES_ENABLED and kind!='abandon':
        done=db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=26770',(uid,)).fetchone()
        if kind!='claim' or not done:raise ValueError('Housing quest writer held')

def admitted(db,uid,account_id,operation,generation):
    # Only the same active SQL writer that inserted this exact admission calls
    # here. No packet, clear event, old room row or client counter supplies75.
    if not WRITES_ENABLED:return []
    if not db.in_transaction:raise ValueError('Housing quest shared writer required')
    row=db.execute('SELECT owner,account_id,generation,quest_generation FROM housing_room_admissions WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:3]!=(uid,account_id,generation):raise ValueError('Housing admission proof missing')
    current=db.execute('SELECT accepted_at,generation,objectives FROM character_quests WHERE owner=? AND quest=26770',(uid,)).fetchone()
    if current is None or row[3]!=current[1]:return []
    counts={int(k):v for k,v in json.loads(current[2]).items()}
    if counts not in({26770:0},{26770:1}):raise ValueError('Housing objective saved integrity')
    if counts[26770]:return []
    counts[26770]=1
    db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=26770 AND generation=?',(json.dumps(counts,sort_keys=True),uid,current[1]))
    from els_server.protocol.quest_messages import progress
    return [progress([dict(id=26770,owner=uid,accepted_at=current[0],generation=current[1],objectives=counts)])]
