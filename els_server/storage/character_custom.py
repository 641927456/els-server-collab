"""Atomic qualified permanent custom-book registration and owned selection."""
import hashlib,json,sqlite3,time
from contextlib import closing
from els_server.domain.character_custom import catalog,canonical,free_catalog,free_ids,slot_value,selection_type,FACE_UNITS
from els_server.protocol import character_custom_messages as wire
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items

OWNED='character_custom_permanent'
SELECTED='character_custom_permanent_selection'
SIDE_SELECTED='character_custom_permanent_selection_slots'
FACE_SELECTED='character_custom_permanent_face_selection'
POINT_SELECTED='character_custom_secret_pointmark_selection'

def exists(db,name):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent (owner INTEGER NOT NULL REFERENCES characters(uid),custom_id INTEGER NOT NULL,source_template INTEGER NOT NULL,PRIMARY KEY(owner,custom_id))')
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent_selection (owner INTEGER PRIMARY KEY REFERENCES characters(uid),custom_id INTEGER NOT NULL CHECK(custom_id>=0))')

def snapshot(db,owner):
    owner=character_uid(owner);owned={};selected={}
    if exists(db,OWNED):
        for cid,book in db.execute('SELECT custom_id,source_template FROM character_custom_permanent WHERE owner=? ORDER BY custom_id',(owner,)):
            if book not in catalog() or catalog()[book]['custom_id']!=cid:raise ValueError('Saved custom source qualification')
            family=catalog()[book]['type']
            if family==2:face_requirement(db,owner,catalog()[book])
            owned.setdefault(family,[]).append(canonical(cid))
    if exists(db,SELECTED):
        row=db.execute('SELECT custom_id FROM character_custom_permanent_selection WHERE owner=?',(owner,)).fetchone()
        if row:
            role=db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
            if role is None or role[0]!=1:raise ValueError('Saved custom role identity')
            if row[0] in free_ids(role[1]):selected={1:canonical(row[0])}
            elif row[0] in free_catalog().values():
                # A later career change may invalidate an ancestor choice.
                # Project native current-career default, retaining the save row;
                # never give free ownership, consume a book or rewrite a career.
                selected={1:canonical(0)}
            elif any(v['custom_id']==row[0] for v in owned.get(1,[])):selected={1:canonical(row[0])}
            else:raise ValueError('Saved custom selection is not owned')
    if exists(db,SIDE_SELECTED):
        side=db.execute('SELECT slot,custom_id FROM character_custom_permanent_selection_slots WHERE owner=? ORDER BY slot',(owner,)).fetchall()
        if side:
            role=db.execute('SELECT unit_type,unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
            if role is None or role[0]!=1:raise ValueError('Saved custom role identity')
            for slot,cid in side:
                if slot==1:raise ValueError('Side selection cannot replace original slot1')
                value=slot_value(slot,canonical(cid));family=selection_type(slot)
                if cid not in free_ids(role[1],slot) and value not in owned.get(family,[]):raise ValueError('Saved custom side selection is not owned')
                selected[slot]=value
    if exists(db,FACE_SELECTED):
        row=db.execute('SELECT custom_id FROM character_custom_permanent_face_selection WHERE owner=?',(owner,)).fetchone()
        if row:
            value=slot_value(2,canonical(row[0]))
            if value not in owned.get(2,[]):raise ValueError('Saved face selection is not owned')
            selected[2]=value
    if exists(db,POINT_SELECTED):
        row=db.execute('SELECT custom_id FROM character_custom_secret_pointmark_selection WHERE owner=?',(owner,)).fetchone()
        if row:
            value=slot_value(28,canonical(row[0]))
            if value not in owned.get(28,[]):raise ValueError('Saved PointMark selection is not owned')
            selected[28]=value
    return dict(owned=owned,selected=selected)

def initialize_side(db):
    # Additive only: never migrate/rebuild the original owner-PK slot1 table.
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent_selection_slots (owner INTEGER NOT NULL REFERENCES characters(uid),slot INTEGER NOT NULL CHECK(slot IN (7,8,13,14,24,25,26,27)),custom_id INTEGER NOT NULL CHECK(custom_id>=0),PRIMARY KEY(owner,slot))')

def initialize_pointmark(db):
    # Additive finite PointMark slot only; no old selection CHECK is rebuilt.
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_secret_pointmark_selection (owner INTEGER PRIMARY KEY REFERENCES characters(uid),custom_id INTEGER NOT NULL CHECK(custom_id=19002))')

def initialize_face(db):
    # Additive face-only storage; preserve both old selection tables and CHECKs.
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent_face_selection (owner INTEGER PRIMARY KEY REFERENCES characters(uid),custom_id INTEGER NOT NULL CHECK(custom_id>0))')


def face_requirement(db,owner,rule):
    role=db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(owner,)).fetchone()
    if role is None or rule['type']!=2 or role[0]!=rule['unit_type'] or role[0] not in FACE_UNITS:
        raise ValueError('Face source/role family')
    from els_server.game_data import client_data
    from els_server.domain.equipment_requirements import class_matches
    raw=client_data().item(rule['book'])['record']
    if (hashlib.sha256(raw).hexdigest()!=rule['native_item_sha256'] or role[2]<raw[209]
        or raw[210]!=role[0] or not class_matches(role[1],raw[211])):
        raise ValueError('Face native source/level/class restriction')


def identity(db,owner,account_id,family=1):
    owner=character_uid(owner)
    if type(account_id) is not int or not 0<account_id<2**63:raise ValueError('Custom account identity')
    row=db.execute('SELECT c.unit_type,c.unit_class,c.level FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(owner,account_id)).fetchone()
    if row is None or (row[0] not in FACE_UNITS if family==2 else row[0] not in range(1,16) if family==28 else row[0]!=1):raise ValueError('Custom owner role qualification')
    if exists(db,'character_lifecycle'):
        state=db.execute('SELECT requested_at,finalized_at FROM character_lifecycle WHERE uid=?',(owner,)).fetchone()
        if state and any(state):raise ValueError('Custom character is pending/finalized deletion')
    return row

def clock(now):
    value=int(time.time()) if now is None else now
    if type(value) is not int or not 0<=value<2**40:raise ValueError('Custom authoritative clock')
    return value

def _check_receipt(db,operation,owner,kind):
    if db.execute('SELECT owner,kind FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()!=(owner,kind):
        raise ValueError('Custom receipt owner/kind')

def use_book(path,owner,account_id,payload,operation,*,now=None,validate=None,validate_pointmark=None):
    item_uid=use_request(payload);now=clock(now)
    operation='custom-book:'+operation
    owner,digest=_identity(owner,0x219,b'custom-book-v1:'+payload,operation)
    rules=catalog()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        # Return None for other existing 219 consumables, without adding schema.
        old=_previous(db,operation,digest);items=load_items(db,owner)
        source=next((i for i in items if i['uid']==item_uid),None)
        rule=rules.get(source['template']) if source else None
        if old is None and rule is None:return None
        # This callback runs ONLY after recognizing a qualified primary book
        # or its exact durable receipt. Other219 routes retain old behavior.
        if validate is not None:validate()
        receipt_rule=None
        if old is not None:
            raw_receipt=db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()[0]
            before=json.loads(raw_receipt)
            if len(before)!=1 or before[0]['uid']!=item_uid or before[0]['template'] not in rules:raise ValueError('Custom book receipt source')
            receipt_rule=rules[before[0]['template']]
        def pointmark_check():
            if (receipt_rule or rule)['type']==28 and validate_pointmark is not None:validate_pointmark()
        pointmark_check()
        role=identity(db,owner,account_id,(receipt_rule or rule)['type'])
        if (receipt_rule or rule)['type']==2:face_requirement(db,owner,receipt_rule or rule)
        balance=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if balance is None:raise ValueError('Custom owner reward balance')
        if old is not None:
            _check_receipt(db,operation,owner,0x219)
            value=canonical(rules[before[0]['template']]['custom_id'])
            if value not in snapshot(db,owner)['owned'].get(rules[before[0]['template']]['type'],[]):raise ValueError('Custom receipt lacks registered ownership')
            positions=list(dict.fromkeys([*old,*[(i['group'],i['slot']) for i in items if i['uid']==item_uid]]))
            current={(i['group'],i['slot']):i for i in items}
            events=[use_ack([(p,current.get(p)) for p in positions],ed=balance[0]),wire.registered(value)]
            for event in events:encode_event(event)
            if validate is not None:validate()
            pointmark_check()
            return dict(replayed=True,events=events)
        if source['group']!=4 or source.get('sealed',False) or source.get('seal_used',0) or 'expires_at' in source:
            raise ValueError('Only permanent unsealed owned primary custom books are admitted')
        from els_server.domain.item_locks import require_unlocked
        from els_server.domain.item_expiration import require_current
        require_unlocked(source,now=now);require_current(source,now=now)
        from els_server.game_data import client_data
        raw=client_data().item(source['template'])['record']
        from els_server.domain.equipment_requirements import class_matches
        if role[2]<raw[209] or raw[210] not in (0,role[0]) or not class_matches(role[1],raw[211]):raise ValueError('Custom book native role/level restriction')
        value=canonical(rule['custom_id'])
        if value in snapshot(db,owner)['owned'].get(rule['type'],[]):raise ValueError('Custom already registered')
        if balance[1]>=2**63-1:raise ValueError('Custom inventory revision overflow')
        remaining=dict(source,count=source['count']-1) if source['count']>1 else None
        events=[use_ack([((source['group'],source['slot']),remaining)],source['template'],balance[0]),wire.registered(value)]
        for event in events:encode_event(event)
        if validate is not None:validate()
        pointmark_check()
        initialize(db)
        db.execute('INSERT INTO character_custom_permanent VALUES (?,?,?)',(owner,value['custom_id'],source['template']))
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,owner))
        else:
            from els_server.storage.item_expiration import forget
            from els_server.storage.item_locks import forget as forget_lock
            forget(db,item_uid);forget_lock(db,item_uid)
            if exists(db,'item_seals'):db.execute('DELETE FROM item_seals WHERE item_uid=?',(item_uid,))
            db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item_uid,owner))
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        load_items(db,owner);snapshot(db,owner)
        _commit(db,operation,digest,owner,0x219,[(source['group'],source['slot'])],[source],[remaining] if remaining else [])
        return dict(replayed=False,events=events)

def select(path,owner,account_id,payload,operation,*,now=None,validate=None):
    slot,value=wire.request_slot(payload);now=clock(now);operation='custom-select:'+operation
    owner,digest=_identity(owner,0x4cb,payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');role=identity(db,owner,account_id,selection_type(slot))
        if validate is not None:validate()
        old=_previous(db,operation,digest);current=snapshot(db,owner)
        family=selection_type(slot)
        if old is None and value['custom_id'] not in free_ids(role[1],slot) and value not in current['owned'].get(family,[]):
            raise ValueError('Custom Apply requires registered ownership or current-career free eligibility')
        if old is not None and slot not in current['selected']:raise ValueError('Custom receipt lacks selected slot')
        selected={slot:current['selected'][slot]} if old is not None else {slot:value}
        if old is not None:_check_receipt(db,operation,owner,0x4cb)
        from els_server.storage.titles import snapshot as title_snapshot
        title=title_snapshot(db,owner,now)['title']
        events=[wire.acknowledgement(selected),wire.selected_notice(owner,title,selected)]
        for event in events:encode_event(event)
        if validate is not None:validate()
        if old is None:
            if slot==1:
                initialize(db)
                db.execute('INSERT INTO character_custom_permanent_selection VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET custom_id=excluded.custom_id',(owner,value['custom_id']))
            elif slot==28:
                initialize_pointmark(db)
                db.execute('INSERT INTO character_custom_secret_pointmark_selection VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET custom_id=excluded.custom_id',(owner,value['custom_id']))
            elif slot==2:
                initialize_face(db)
                db.execute('INSERT INTO character_custom_permanent_face_selection VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET custom_id=excluded.custom_id',(owner,value['custom_id']))
            else:
                initialize_side(db)
                db.execute('INSERT INTO character_custom_permanent_selection_slots VALUES (?,?,?) ON CONFLICT(owner,slot) DO UPDATE SET custom_id=excluded.custom_id',(owner,slot,value['custom_id']))
            _commit(db,operation,digest,owner,0x4cb,[],[],[])
        snapshot(db,owner)
        return dict(replayed=old is not None,events=events)
