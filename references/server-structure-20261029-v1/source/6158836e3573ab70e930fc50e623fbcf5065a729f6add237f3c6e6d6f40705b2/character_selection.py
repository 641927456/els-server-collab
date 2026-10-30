"""Account-scoped, atomic character deployment/order preferences."""
import json,sqlite3
from contextlib import closing
from els_server.protocol.character_selection_messages import validate_selection

def _owned(db,account_id):
    if type(account_id) is not int or not 1<=account_id<2**63:raise ValueError('Account identity')
    from els_server.storage.character_lifecycle import visible_ids
    return visible_ids(db,account_id)

def _state(db,account_id,owned):
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_selection_preferences'").fetchone()
    old=db.execute('SELECT deployed,character_order,revision FROM character_selection_preferences WHERE account_id=?',(account_id,)).fetchone() if exists else None
    if old:
        deployed=json.loads(old[0]);order=json.loads(old[1])
        # Preserve deliberate empty slots and append newly created roles. Removed
        # identities cannot survive in a scene or be inherited by another account.
        deployed=tuple(uid if uid in owned else 0 for uid in deployed)
        order=tuple(uid for uid in order if uid in owned)+tuple(uid for uid in owned if uid not in order)
        revision=old[2]
    else:
        # Existing saves have no per-role login timestamps. Deterministic UID
        # order is a documented local fallback, not invented login history.
        order=owned;deployed=owned[:5];revision=0
    from els_server.storage.character_lifecycle import states
    blocked={uid for uid,s in states(db,owned).items() if s['requested_at'] or s['finalized_at']}
    deployed=tuple(0 if uid in blocked else uid for uid in deployed)
    deployed,order=validate_selection(deployed,order,owned)
    return dict(deployed=list(deployed),order=list(order),revision=revision)

def snapshot(path,account_id):
    with closing(sqlite3.connect(path,timeout=10)) as db:
        db.execute('BEGIN')
        return _state(db,account_id,_owned(db,account_id))

def save(path,account_id,deployed,order):
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        owned=_owned(db,account_id)
        deployed,order=validate_selection(deployed,order,owned)
        from els_server.storage.character_lifecycle import states
        blocked={uid for uid,s in states(db,owned).items() if s['requested_at'] or s['finalized_at']}
        if any(uid in blocked for uid in deployed if uid):raise ValueError('Pending deletion character cannot be deployed')
        previous=_state(db,account_id,owned)
        # Validation precedes schema creation, so rejected requests have no write.
        db.execute('CREATE TABLE IF NOT EXISTS character_selection_preferences (account_id INTEGER PRIMARY KEY CHECK(account_id>0),deployed TEXT NOT NULL,character_order TEXT NOT NULL,revision INTEGER NOT NULL CHECK(revision>=0))')
        revision=previous['revision']+int(list(deployed)!=previous['deployed'] or list(order)!=previous['order'])
        db.execute('INSERT INTO character_selection_preferences VALUES (?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET deployed=excluded.deployed,character_order=excluded.character_order,revision=excluded.revision',(account_id,json.dumps(deployed),json.dumps(order),revision))
        return dict(deployed=list(deployed),order=list(order),revision=revision)
