"""Atomic selected force ownership and source-book consumption, per character."""
import sqlite3,time
from contextlib import closing
from els_server.domain.boosting_2026_force_inventory import catalog,owned,learned_notice,seal_used,ForceRuleError
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items,owned_template
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.protocol.career_messages import use_request,use_ack
from els_server.protocol.protocol_codec import encode_event

TABLE='selected_2026_force_inventory'
CHANGE_TABLE='selected_2026_change_force_inventory'

COMMON_LEARNING_ENABLED=True

def initialize_change(db):
    if not db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Change force schema requires caller transaction and enabled foreign keys')
    db.execute('''CREATE TABLE IF NOT EXISTS selected_2026_change_force_inventory (
        owner INTEGER NOT NULL REFERENCES characters(uid), skill INTEGER NOT NULL,
        rank INTEGER NOT NULL CHECK(rank=1), source_template INTEGER NOT NULL,
        seal_used INTEGER NOT NULL CHECK(seal_used BETWEEN 0 AND 1),
        PRIMARY KEY(owner,skill,rank), UNIQUE(owner,source_template))''')

def initialize(db):
    if not db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Force schema requires caller transaction and enabled foreign keys')
    db.execute('''CREATE TABLE IF NOT EXISTS selected_2026_force_inventory (
        owner INTEGER NOT NULL REFERENCES characters(uid), skill INTEGER NOT NULL,
        rank INTEGER NOT NULL, source_template INTEGER NOT NULL,
        seal_used INTEGER NOT NULL DEFAULT 0 CHECK(seal_used BETWEEN 0 AND 3 AND ((rank=3 AND seal_used=0) OR (rank=4 AND seal_used<=3) OR (rank=5 AND seal_used<=1) OR (rank=6 AND seal_used=0))),
        PRIMARY KEY(owner,skill,rank),
        CHECK((skill=900401 AND rank=3 AND source_template=295707) OR
              (skill=900402 AND rank=3 AND source_template=295712) OR
              (skill=900406 AND rank=3 AND source_template=306002) OR
              (skill=900402 AND rank=5 AND source_template=295714) OR
              (skill=900406 AND rank=5 AND source_template=306004) OR
              (skill=900401 AND rank=4 AND source_template=295708) OR
              (skill=900402 AND rank=4 AND source_template=295713) OR
              (skill=900406 AND rank=4 AND source_template=306003) OR
              (skill=900401 AND rank=5 AND source_template=295709) OR
              (skill=900214 AND rank=5 AND source_template=295729) OR
              (skill=900234 AND rank=5 AND source_template=295739) OR
              (skill=900244 AND rank=5 AND source_template=295744) OR
              (skill=900269 AND rank=5 AND source_template=311066) OR
              (skill=900274 AND rank=5 AND source_template=311515) OR
              (skill=900279 AND rank=5 AND source_template=311521) OR
              (skill=900405 AND rank=6 AND source_template=295762) OR
              (skill=900408 AND rank=5 AND source_template=311512) OR
              (skill=900409 AND rank=5 AND source_template=311518) OR
              (skill=900410 AND rank=5 AND source_template=311524) OR
              (skill=900411 AND rank=5 AND source_template=311527) OR
              (skill=900305 AND rank=6 AND source_template=295750)))''')
    columns={row[1] for row in db.execute('PRAGMA table_info(selected_2026_force_inventory)')}
    if 'seal_used' not in columns:
        # Earlier candidate records always projected zero and could not
        # retain nonzero history. Preserve those legacy wire values.
        db.execute('ALTER TABLE selected_2026_force_inventory ADD COLUMN seal_used INTEGER NOT NULL DEFAULT 0 CHECK(seal_used BETWEEN 0 AND 3 AND ((rank=3 AND seal_used=0) OR (rank=4 AND seal_used<=3) OR (rank=5 AND seal_used<=1) OR (rank=6 AND seal_used=0)))')
    from els_server.storage.force_rank4_schema import migrate
    migrate(db)


def saved(db,owner):
    owner=character_uid(owner)
    values=[]
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(TABLE,)).fetchone():
        columns={row[1] for row in db.execute('PRAGMA table_info(selected_2026_force_inventory)')}
        field='seal_used' if 'seal_used' in columns else '0'
        values.extend(dict(skill=s,rank=r,template=t,seal_used=u) for s,r,t,u in db.execute('SELECT skill,rank,source_template,'+field+' FROM selected_2026_force_inventory WHERE owner=? ORDER BY skill,rank',(owner,)))
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(CHANGE_TABLE,)).fetchone():
        from els_server.domain.change_force_inventory import catalog as changes
        for s,r,t,u in db.execute('SELECT skill,rank,source_template,seal_used FROM selected_2026_change_force_inventory WHERE owner=? ORDER BY skill,rank',(owner,)):
            if t not in changes(include_starters=True) or (s,r)!=(changes(include_starters=True)[t]['skill'],1):raise ValueError('Saved change force exact native identity')
            values.append(dict(skill=s,rank=r,template=t,seal_used=u))
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='career_box_common_force'").fetchone():
        for skill,rank,template,used in db.execute('SELECT skill,rank,source_template,seal_used FROM career_box_common_force WHERE owner=?',(owner,)):
            if(skill,rank,template,used)!=(900224,5,295734,0):raise ValueError('Starter common force identity')
            values.append(dict(skill=skill,rank=rank,template=template,seal_used=used))
    return owned(dict(force_inventory=values))

def snapshot(path,owner):
    with closing(sqlite3.connect(path)) as db:return saved(db,owner)

def use_book(path,owner,account_id,payload,operation,*,now=None,session_authorized=True):
    # Internal storage callers are trusted; external native219 always passes a strict session qualification.
    if type(session_authorized)is not bool:raise ValueError('Force session qualification type')
    if not isinstance(operation,str):raise ValueError('Force book operation identity')
    item_uid=use_request(payload);owner,digest=_identity(owner,0x219,b'selected-force-v1:'+payload,'force-book:'+operation);operation='force-book:'+operation
    if type(account_id) is not int or not 0<account_id<2**63:raise ValueError('Force book account identity')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        character=db.execute('SELECT c.unit_class,c.level,c.master,c.unit_type FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(owner,account_id)).fetchone()
        if character is None:raise ValueError('Force book character owner')
        old=_previous(db,operation,digest);balance=db.execute('SELECT ed,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if balance is None:raise ValueError('Force book reward balance')
        if old is not None:
            if db.execute('SELECT owner,kind FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()!=(owner,0x219):raise ValueError('Force book receipt owner/kind')
            if not session_authorized:raise ValueError('Obsolete force book session')
            from els_server.storage.item_actor import require_active_character
            require_active_character(db,owner)
            event=use_ack(ed=balance[0]);encode_event(event)
            return dict(replayed=True,events=[event])
        rule=catalog().get(owned_template(db,owner,item_uid))
        if rule is None:return None
        if rule.get('native_common')and not COMMON_LEARNING_ENABLED:raise ValueError('New common Force learning paused')
        items=load_items(db,owner);source=next(i for i in items if i['uid']==item_uid)
        if not session_authorized:raise ValueError('Obsolete force book session')
        from els_server.storage.item_actor import require_active_character
        require_active_character(db,owner)
        if source['group']!=4:raise ValueError('Owned force consumable book required')
        if source.get('sealed',False):raise ValueError('Sealed force-book use is unsupported; keep the item unchanged')
        if rule.get('change'):
            from els_server.domain.change_force_admission import LEARNING
            if not LEARNING:raise ValueError('Change force learning admission is closed')
            from els_server.domain.change_force_inventory import for_character
            for_character(source['template'],dict(unit_class=character[0],level=character[1],unit_type=character[3]))
            if 'expires_at' in source:raise ValueError('Only permanent native change books are qualified')
        if source['template'] in (295708,295713,306003,295709,295729,295739,295744,311066,311515,311521,295762,311512,311518,311524,311527,295750) and 'expires_at' in source:raise ValueError('Only permanent manufactured force upgrade books are qualified')
        used=seal_used(source['template'],source.get('seal_used',0))
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        value=int(time.time()) if now is None else now
        if type(value) is not int or not 0<=value<2**40:raise ValueError('Force use epoch')
        require_current(source,now=value);require_unlocked(source,now=value)
        from els_server.domain.character_rules import CLASSES
        if CLASSES[character[0]]['stage']<rule['required_stage'] or character[1]<99:raise ForceRuleError(1903,'Force skills require third job and original book level')
        if rule.get('required_master') and not character[2]:raise ForceRuleError(1903,'Current native book requires Master class')
        previous=saved(db,owner)
        if any((r['skill'],r['rank'])==(rule['skill'],rule['native_rank']) for r in previous):raise ForceRuleError(2034,'Same force name and grade already owned')
        if len(previous)>=36:raise ForceRuleError(2024,'Force inventory is full')
        if balance[1]>=2**63-1:raise ValueError('Force inventory revision overflow')
        remaining=dict(source,count=source['count']-1) if source['count']>1 else None
        events=[use_ack([((source['group'],source['slot']),remaining)],template=source['template'],ed=balance[0]),learned_notice(rule,used,owner=owner)]
        for event in events:encode_event(event)
        if rule.get('change'):
            initialize_change(db)
            db.execute('INSERT INTO selected_2026_change_force_inventory(owner,skill,rank,source_template,seal_used) VALUES (?,?,?,?,?)',(owner,rule['skill'],1,source['template'],used))
        elif rule.get('starter_common'):
            db.execute('CREATE TABLE IF NOT EXISTS career_box_common_force (owner INTEGER PRIMARY KEY REFERENCES characters(uid),skill INTEGER NOT NULL CHECK(skill=900224),rank INTEGER NOT NULL CHECK(rank=5),source_template INTEGER NOT NULL CHECK(source_template=295734),seal_used INTEGER NOT NULL CHECK(seal_used=0))')
            db.execute('INSERT INTO career_box_common_force VALUES (?,?,?,?,?)',(owner,rule['skill'],rule['native_rank'],source['template'],used))
        else:
            initialize(db)
            db.execute('INSERT INTO selected_2026_force_inventory(owner,skill,rank,source_template,seal_used) VALUES (?,?,?,?,?)',(owner,rule['skill'],rule['native_rank'],source['template'],used))
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,owner))
        else:
            from els_server.storage.item_expiration import forget
            from els_server.storage.item_locks import forget as forget_lock
            forget(db,item_uid);forget_lock(db,item_uid)
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_seals'").fetchone():db.execute('DELETE FROM item_seals WHERE item_uid=?',(item_uid,))
            db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item_uid,owner))
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        load_items(db,owner);saved(db,owner)
        _commit(db,operation,digest,owner,0x219,[(source['group'],source['slot'])],[source],[remaining] if remaining else [])
        return dict(replayed=False,events=events)
