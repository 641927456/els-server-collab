"""Atomic qualified permanent custom-book registration and owned selection."""
import hashlib,json,sqlite3,time,struct
from contextlib import closing
from els_server.domain.character_custom import catalog,canonical,free_ids,slot_value,selection_type,qualified,book_values,custom_rules,data
from els_server.protocol import character_custom_messages as wire
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,owned_template

class CustomUseError(ValueError):
    """An expected refusal with an existing native result message."""
    def __init__(self,message,result):
        super().__init__(message)
        self.result=result

OWNED='character_custom_permanent' 
SELECTED='character_custom_permanent_selection'
SIDE_SELECTED='character_custom_permanent_selection_slots'
FACE_SELECTED='character_custom_permanent_face_selection'

def exists(db,name):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent (owner INTEGER NOT NULL REFERENCES characters(uid),custom_id INTEGER NOT NULL,source_template INTEGER NOT NULL,PRIMARY KEY(owner,custom_id))')
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent_selection (owner INTEGER PRIMARY KEY REFERENCES characters(uid),custom_id INTEGER NOT NULL CHECK(custom_id>=0))')

EXTRA_SELECTED='character_custom_permanent_extra_selection'
EXTRA_SLOTS=frozenset({3,4,5,6,10,11,12,15,19,20,21,22,23})

def initialize_extra(db):
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent_extra_selection(owner INTEGER NOT NULL REFERENCES characters(uid),slot INTEGER NOT NULL,custom_id INTEGER NOT NULL CHECK(custom_id>=0),variant INTEGER NOT NULL CHECK(variant BETWEEN 1 AND 3),PRIMARY KEY(owner,slot))')

def snapshot(db,owner):
    owner=character_uid(owner);owned={};selected={}
    role=db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(owner,)).fetchone()
    if role is None:raise ValueError('Custom role identity')
    if exists(db,OWNED):
        for cid,book in db.execute('SELECT custom_id,source_template FROM character_custom_permanent WHERE owner=? ORDER BY custom_id',(owner,)):
            rule=catalog().get(book)
            if rule is None or cid not in rule['custom_ids']:raise ValueError('Saved custom source qualification')
            book_requirement(role,rule,registration=False)
            owned.setdefault(rule['type'],[]).append(canonical(cid))
    if exists(db,'character_custom_permanent_abilities'):
        for cid,ability in db.execute('SELECT custom_id,ability FROM character_custom_permanent_abilities WHERE owner=?',(owner,)):
            value=canonical(cid,ability=ability);family=custom_rules()[cid]['type']
            rows=owned.setdefault(family,[])
            found=next((i for i,v in enumerate(rows)if v['custom_id']==cid),None)
            if found is None:
                if cid not in free_ids(role[1],family):continue
                rows.append(value)
            else:rows[found]=value
    saved=[]
    if exists(db,SELECTED):saved.extend((1,cid,None)for cid, in db.execute('SELECT custom_id FROM character_custom_permanent_selection WHERE owner=?',(owner,)))
    if exists(db,SIDE_SELECTED):saved.extend((slot,cid,None)for slot,cid in db.execute('SELECT slot,custom_id FROM character_custom_permanent_selection_slots WHERE owner=?',(owner,)))
    if exists(db,FACE_SELECTED):saved.extend((2,cid,None)for cid, in db.execute('SELECT custom_id FROM character_custom_permanent_face_selection WHERE owner=?',(owner,)))
    if exists(db,EXTRA_SELECTED):
        extra=list(db.execute('SELECT slot,custom_id,variant FROM character_custom_permanent_extra_selection WHERE owner=?',(owner,)))
        keys={r[0]for r in extra};saved=[r for r in saved if r[0]not in keys]+extra
    free_rules={r['custom_id']for r in data()['free_customs']}
    for slot,cid,variant in saved:
        value=slot_value(slot,canonical(cid,variant=variant))
        registered=next((v for v in owned.get(selection_type(slot),[])if v['custom_id']==cid),None)
        if registered is not None:value=registered
        if qualified(role,slot,value,owned):selected[slot]=value
        elif cid in free_rules:
            # A career change does not turn an obsolete free choice into ownership.
            if selection_type(slot)==1:selected[slot]=canonical(0,variant=2 if role[0]==10 else 1)
        else:raise ValueError('Saved custom selection is not owned or career-qualified')
    return dict(owned=owned,selected=selected)

def initialize_side(db):
    # Additive only: never migrate/rebuild the original owner-PK slot1 table.
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent_selection_slots (owner INTEGER NOT NULL REFERENCES characters(uid),slot INTEGER NOT NULL CHECK(slot IN (7,8,13,14,24,25,26,27)),custom_id INTEGER NOT NULL CHECK(custom_id>=0),PRIMARY KEY(owner,slot))')

def initialize_face(db):
    # Additive face-only storage; preserve both old selection tables and CHECKs.
    db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent_face_selection (owner INTEGER PRIMARY KEY REFERENCES characters(uid),custom_id INTEGER NOT NULL CHECK(custom_id>0))')


def book_requirement(role,rule,*,registration=True):
    from els_server.game_data import client_data
    from els_server.domain.equipment_requirements import class_matches
    raw=client_data().item(rule['book'])['record']
    if hashlib.sha256(raw).hexdigest()!=rule['native_item_sha256']:raise ValueError('Custom native source changed')
    if role[0]not in rule['units'] or raw[210]not in(0,role[0]):raise CustomUseError('Custom book native role restriction',285)
    if registration:
        if role[2]<raw[209]:raise CustomUseError('Custom book native level restriction',502)
        if not class_matches(role[1],rule.get('required_class',raw[211])):raise CustomUseError('Custom book native role restriction',285)

def identity(db,owner,account_id,family=1):
    from els_server.domain.character_rules import CLASSES
    from els_server.game_data import client_data
    owner=character_uid(owner)
    if type(account_id)is not int or not 0<account_id<2**63:raise ValueError('Custom account identity')
    role=db.execute('SELECT c.unit_type,c.unit_class,c.level FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(owner,account_id)).fetchone()
    if role is None or role[1]not in CLASSES or client_data().unit(role[1])['unitType']!=role[0]:raise ValueError('Custom owner role qualification')
    if exists(db,'character_lifecycle'):
        state=db.execute('SELECT requested_at,finalized_at FROM character_lifecycle WHERE uid=?',(owner,)).fetchone()
        if state and any(state):raise ValueError('Custom character is pending/finalized deletion')
    return role

def clock(now):
    value=int(time.time()) if now is None else now
    if type(value) is not int or not 0<=value<2**40:raise ValueError('Custom authoritative clock')
    return value

def _check_receipt(db,operation,owner,kind):
    if db.execute('SELECT owner,kind FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()!=(owner,kind):
        raise ValueError('Custom receipt owner/kind')

def use_book(path,owner,account_id,payload,operation,*,now=None,validate=None):
    if not isinstance(payload,bytes)or len(payload)!=29:return None
    item_uid,target,family,ability,length,flag=struct.unpack('>QQiiIB',payload)
    if not 0<item_uid<2**63:return None
    now=clock(now)
    operation='custom-book:'+operation
    owner,digest=_identity(owner,0x219,b'custom-book-v1:'+payload,operation)
    rules=catalog()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        # Return None for other existing 219 consumables, without adding schema.
        old=_previous(db,operation,digest)
        template=owned_template(db,owner,item_uid);rule=rules.get(template)
        if old is None and rule is None:return None
        items=load_items(db,owner)
        source=next((i for i in items if i['uid']==item_uid),None)
        # This callback runs ONLY after recognizing a qualified primary book
        # or its exact durable receipt. Other219 routes retain old behavior.
        if validate is not None:validate()
        receipt_rule=None
        if old is not None:
            raw_receipt=db.execute('SELECT before_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()[0]
            before=json.loads(raw_receipt)
            if len(before)!=1 or before[0]['uid']!=item_uid or before[0]['template'] not in rules:raise ValueError('Custom book receipt source')
            receipt_rule=rules[before[0]['template']]
        role=identity(db,owner,account_id,(receipt_rule or rule)['type'])
        book_requirement(role,receipt_rule or rule,registration=old is None)
        source_rule=receipt_rule or rule
        # Native221F5D0 ->22611D0 ->C595C0 carries the source CustomID/type.
        # Empty optional parameters remain the ordinary shared219 shape.
        if length or flag or ((target,family,ability)!=(0,0,0)and
                (target not in source_rule['custom_ids']or family!=source_rule['type']or ability<0)):
            raise CustomUseError('Custom registration source parameters',500)
        current=snapshot(db,owner)
        # This is cached existing ability metadata, never an assignment request.
        if ability:canonical(target,ability=ability)
        balance=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if balance is None:raise ValueError('Custom owner reward balance')
        if old is not None:
            _check_receipt(db,operation,owner,0x219)
            values=book_values(rules[before[0]['template']]);value=values[0]
            saved={v['custom_id']:v for v in current['owned'].get(rules[before[0]['template']]['type'],[])}
            if any(v['custom_id']not in saved for v in values):raise ValueError('Custom receipt lacks registered ownership')
            values=[saved[v['custom_id']]for v in values]
            positions=list(dict.fromkeys([*old,*[(i['group'],i['slot']) for i in items if i['uid']==item_uid]]))
            current={(i['group'],i['slot']):i for i in items}
            events=[use_ack([(p,current.get(p)) for p in positions],ed=balance[0]),*[wire.registered(v)for v in values]]
            for event in events:encode_event(event)
            if validate is not None:validate()
            return dict(replayed=True,events=events)
        if source['group']!=4 or source.get('sealed',False) or source.get('seal_used',0) or 'expires_at' in source:
            raise CustomUseError('Only permanent unsealed owned primary custom books are admitted',500)
        from els_server.domain.item_locks import require_unlocked
        from els_server.domain.item_expiration import require_current
        if source.get('lock_until',0)>now:raise CustomUseError('Custom source is locked',2948)
        require_unlocked(source,now=now);require_current(source,now=now)
        values=book_values(rule);value=values[0]
        owned={v['custom_id']for v in current['owned'].get(rule['type'],[])}
        values=[v for v in values if v['custom_id']not in owned]
        if not values:raise CustomUseError('Custom already registered',1492)
        if balance[1]>=2**63-1:raise ValueError('Custom inventory revision overflow')
        remaining=dict(source,count=source['count']-1) if source['count']>1 else None
        events=[use_ack([((source['group'],source['slot']),remaining)],source['template'],balance[0]),*[wire.registered(v)for v in values]]
        for event in events:encode_event(event)
        if validate is not None:validate()
        initialize(db)
        db.executemany('INSERT INTO character_custom_permanent VALUES (?,?,?)',[(owner,v['custom_id'],source['template'])for v in values])
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
        if old is None and not qualified(role,slot,value,current['owned']):
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
            from els_server.domain.ariel_attendance_mark import clear_ordinary
            clear_ordinary(db,owner,slot)
            if slot in EXTRA_SLOTS or role[0]==10:
                initialize_extra(db)
                db.execute('INSERT INTO character_custom_permanent_extra_selection VALUES (?,?,?,?) ON CONFLICT(owner,slot) DO UPDATE SET custom_id=excluded.custom_id,variant=excluded.variant',(owner,slot,value['custom_id'],value['variant']))
            elif slot==1:
                initialize(db)
                db.execute('INSERT INTO character_custom_permanent_selection VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET custom_id=excluded.custom_id',(owner,value['custom_id']))
            elif slot==2:
                initialize_face(db)
                db.execute('INSERT INTO character_custom_permanent_face_selection VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET custom_id=excluded.custom_id',(owner,value['custom_id']))
            else:
                initialize_side(db)
                db.execute('INSERT INTO character_custom_permanent_selection_slots VALUES (?,?,?) ON CONFLICT(owner,slot) DO UPDATE SET custom_id=excluded.custom_id',(owner,slot,value['custom_id']))
            _commit(db,operation,digest,owner,0x4cb,[],[],[])
        snapshot(db,owner)
        return dict(replayed=old is not None,events=events)

def opening_info(path,owner,account_id,*,validate=None):
    """Read current identity and project the published normal cash catalog.

    Both cash availability lists are genuinely empty in the same D79 catalog.
    Owned custom IDs and present books remain in their existing 31/4CD/2A
    paths; no schema, grant, registration, selection or payment occurs here.
    """
    from pathlib import Path
    from els_server.protocol.shop_messages import empty_catalog_ack
    owner=character_uid(owner)
    if type(account_id)is not int or not 0<account_id<2**63:raise ValueError('Custom opening account')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        if validate is not None:validate()
        role=db.execute('SELECT c.uid FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(owner,account_id)).fetchone()
        if role is None:raise ValueError('Custom opening current owner')
        if exists(db,'character_lifecycle'):
            state=db.execute('SELECT requested_at,finalized_at FROM character_lifecycle WHERE uid=?',(owner,)).fetchone()
            if state and any(state):raise ValueError('Custom opening deleted owner')
        cash_catalog=empty_catalog_ack();encode_event(cash_catalog)
        event=wire.opening_information(cash_catalog);encode_event(event)
        if validate is not None:validate()
        return [event]

def assign_ability(path,owner,account_id,payload,operation,*,now=None,validate=None):
    source_uid,cid,family,ability=wire.socket_request(payload)
    now=clock(now);operation='custom-ability:'+operation
    owner,digest=_identity(owner,0x219,payload,operation)
    from els_server.domain.character_custom import custom_type
    if custom_type(cid)!=family:raise ValueError('Custom socket family')
    value=canonical(cid,ability=ability)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        role=identity(db,owner,account_id,family)
        if validate is not None:validate()
        old=_previous(db,operation,digest);state=snapshot(db,owner)
        current=next((v for v in state['owned'].get(family,[])if v['custom_id']==cid),None)
        if current is None:
            if cid not in free_ids(role[1],family):raise CustomUseError('Custom ability requires owned customization',500)
            current=canonical(cid)
        items=load_items(db,owner);changes=[];before=[];after=[]
        balance=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if balance is None:raise ValueError('Custom ability balance identity')
        if old is not None:
            _check_receipt(db,operation,owner,0x219)
            positions=list(dict.fromkeys([*old,*[(i['group'],i['slot'])for i in items if i['uid']==source_uid]]))
            by_position={(i['group'],i['slot']):i for i in items}
            changes=[(p,by_position.get(p))for p in positions];value=current
        elif (custom_rules()[cid]['ability_group'] or 0)==0 or current['ability']:
            source=next((i for i in items if i['uid']==source_uid),None)
            if source is None or source['template']!=295995 or source['group']!=4:raise CustomUseError('Custom ability needs Magic Scroll',500)
            if source.get('sealed',False)or source.get('seal_used',0):raise CustomUseError('Custom ability source sealed',500)
            from els_server.domain.item_locks import require_unlocked
            from els_server.domain.item_expiration import require_current
            if source.get('lock_until',0)>now:raise CustomUseError('Custom ability source locked',2948)
            require_unlocked(source,now=now);require_current(source,now=now)
            # Retained inventory readers require the exact stored shape. Build
            # the post-consumption delta through the same owned reader.
            from els_server.domain.retained_native_consumables import read_existing
            remaining=read_existing(dict(source,count=source['count']-1))if source['count']>1 else None
            changes=[((source['group'],source['slot']),remaining)];before=[source];after=[remaining]if remaining else []
        selected={slot:dict(v,ability=value['ability'])for slot,v in state['selected'].items()if v['custom_id']==cid}
        events=[use_ack(changes,295995 if before else 0,balance[0]),wire.registered(value)]
        if selected:
            from els_server.storage.titles import snapshot as title_snapshot
            events.append(wire.selected_notice(owner,title_snapshot(db,owner,now)['title'],selected))
        for event in events:encode_event(event)
        if validate is not None:validate()
        if old is None:
            if balance[1]>=2**63-1:raise ValueError('Custom ability inventory revision overflow')
            db.execute('CREATE TABLE IF NOT EXISTS character_custom_permanent_abilities(owner INTEGER NOT NULL REFERENCES characters(uid),custom_id INTEGER NOT NULL,ability INTEGER NOT NULL CHECK(ability>0),PRIMARY KEY(owner,custom_id))')
            db.execute('INSERT INTO character_custom_permanent_abilities VALUES(?,?,?) ON CONFLICT(owner,custom_id)DO UPDATE SET ability=excluded.ability',(owner,cid,ability))
            if before:
                source=before[0]
                if after:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(source_uid,owner))
                else:
                    from els_server.storage.item_expiration import forget
                    from els_server.storage.item_locks import forget as forget_lock
                    forget(db,source_uid);forget_lock(db,source_uid)
                    if exists(db,'item_seals'):db.execute('DELETE FROM item_seals WHERE item_uid=?',(source_uid,))
                    db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(source_uid,owner))
            db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
            _commit(db,operation,digest,owner,0x219,[p for p,v in changes],before,after)
            load_items(db,owner);snapshot(db,owner)
        return dict(replayed=old is not None,events=events)
