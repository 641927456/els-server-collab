"""Finite52700 activation and collection contributions from current careers."""
from els_server.domain.el_search_collection import QUEST,COST,canonical,current_entry,entry,priority,wire

# Recovery variants replace this one constant; optional readers always remain.
WRITES_ENABLED=True
ACT='character_search_collection_activation'

def exists(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def identity(db,uid,account_id):
    if type(account_id)is not int or not 1<=account_id<2**63:raise ValueError('Collection account identity')
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Collection character owner mismatch')

def is_active(db, uid):
    return exists(db, ACT) and db.execute(
        'SELECT 1 FROM character_search_collection_activation WHERE owner=?', (uid,)).fetchone() is not None

def before_action(db,uid,account_id,kind,guard):
    identity(db,uid,account_id)
    if not callable(guard):raise ValueError('Collection requires current actor lease')
    guard(db)
    # A done claim is a reader/replay even when this finite writer is held.
    completed=exists(db,'completed_quests') and db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(uid,QUEST)).fetchone()
    if not WRITES_ENABLED and kind!='abandon' and not(kind=='claim'and completed):raise ValueError('Collection52700 writer held')
    if kind == 'accept' and not completed and is_active(db, uid):
        raise ValueError('Collection already activated')

def snapshot(db,uid,account_id):
    identity(db,uid,account_id)
    if not exists(db,ACT):return None
    saved=db.execute('''SELECT a.owner,a.account_id,a.source_quest,a.unit_type,a.unit_line,
        a.unit_class,a.transcendental,a.collection_stage,a.created_at,
        c.unit_type,c.unit_class,c.transcendence,c.master
        FROM character_owners o JOIN characters c ON c.uid=o.uid
        JOIN character_search_collection_activation a ON a.owner=c.uid
        WHERE o.account_id=? ORDER BY c.uid''',(account_id,)).fetchall()
    from els_server.storage.character_lifecycle import states
    lifecycle=states(db,(r[0] for r in saved))
    activated=False;registered={}
    for row in saved:
        owner,account,quest,unit,line,cls,trans,stage,at,current_unit,current_cls,transcendence,master=row
        if lifecycle.get(owner,{}).get('finalized_at'):continue
        if account!=account_id or quest!=QUEST or type(at)is not int or not 0<at<2**63:raise ValueError('Collection activation integrity')
        # Keep the original activation as proof of the unlock, not a permanent
        # contribution from the career that happened to activate it.
        canonical(dict(unit_type=unit,line=line,unit_class=cls,transcendental=trans,stage=stage))
        value=entry(current_cls,2 if master else transcendence)
        if value['unit_type']!=current_unit or current_unit!=unit or master and not transcendence:raise ValueError('Collection current career identity')
        activated=activated or owner==uid
        key=(current_unit,value['line'])
        if key not in registered or priority(value)>priority(registered[key]):registered[key]=value
    rows=[registered[key] for key in sorted(registered)]
    if not activated and not rows:return None
    from els_server.storage.el_search_collection_tickets import expiry
    from els_server.storage.collection_synergy import state as synergy_state
    value=dict(active=activated,registered=rows,expiry=expiry(db,uid,account_id),field1d=1,field21=1,**synergy_state(db,uid,account_id,rows))
    wire(value)
    return value

def ensure(db):
    if not db.in_transaction:raise ValueError('Collection requires caller transaction')
    db.execute('CREATE TABLE IF NOT EXISTS character_search_collection_activation (owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL CHECK(account_id>0),source_quest INTEGER NOT NULL CHECK(source_quest=52700),unit_type INTEGER NOT NULL CHECK(unit_type BETWEEN 1 AND 15),unit_line INTEGER NOT NULL CHECK(unit_line BETWEEN 1 AND 4),unit_class INTEGER NOT NULL,transcendental INTEGER NOT NULL CHECK(transcendental BETWEEN 0 AND 2),collection_stage INTEGER NOT NULL CHECK(collection_stage BETWEEN 1 AND 3),created_at INTEGER NOT NULL CHECK(created_at>0))')

def activate(db,uid,account_id,character,now,*,using_book=False):
    if not WRITES_ENABLED:raise ValueError('Collection52700 writer held')
    identity(db,uid,account_id)
    if character['uid']!=uid or character['level']<99 or type(now)is not int or not 0<now<2**63:raise ValueError('Collection activation eligibility')
    before=snapshot(db,uid,account_id)
    if before is not None and before['active']:raise ValueError('Collection already activated')
    value=current_entry(character)
    if using_book:
        from els_server.storage.seal_quests import ensure as ensure_quests
        ensure_quests(db)
        # Both paths satisfy the same unlock. Only the EP path earns a quest completion.
        db.execute('DELETE FROM character_quests WHERE owner=? AND quest=?', (uid, QUEST))
    else:
        from els_server.storage.ep_points import debit
        debit(db,uid,COST)
    ensure(db)
    # The existing schema uses 52700 to identify this unlock. The item-use
    # receipt records the exact book and source slot for a book activation.
    db.execute('INSERT INTO character_search_collection_activation VALUES (?,?,?,?,?,?,?,?,?)',(uid,account_id,QUEST,value['unit_type'],value['line'],value['unit_class'],value['transcendental'],value['stage'],now))
    return snapshot(db,uid,account_id)

def career_changed(db,uid,character):
    # Only a proven existing career writer calls this after its saved change.
    # Never activate, spend EP or create an account entry for an unopened role.
    if not WRITES_ENABLED or not exists(db,ACT):return False
    row=db.execute('SELECT account_id FROM character_search_collection_activation WHERE owner=?',(uid,)).fetchone()
    if row is None:return False
    # The caller has saved the career already. The same read supplies the new
    # account contributions and removes unavailable careers from synergy slots.
    value=snapshot(db,uid,row[0])  # Validate/encode before the career transaction commits.
    from els_server.storage.collection_synergy import retire_unavailable
    retire_unavailable(db,row[0],value['registered'])
    return True
