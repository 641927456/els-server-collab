"""Character/private and account/shared bank instances, with atomic transfers."""
from els_server.storage.item_actor import require_active_character
import json,sqlite3,struct
from contextlib import closing
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,validate_item
from els_server.domain.item_expiration import require_current,expired
from els_server.protocol.bank_messages import transfer_request,transfer_ack,sort_ack
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_state import load_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.bag_capacity import allowances
from els_server.storage.item_instances import remove,insert,next_uid
from els_server.storage.character_schema import character_uid
from els_server.domain.bank_rules import TIERS,expansion_cost,require_storable


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS private_bank_items (
        uid INTEGER PRIMARY KEY, owner INTEGER NOT NULL REFERENCES characters(uid),
        slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 47), item_json TEXT NOT NULL,
        UNIQUE(owner,slot))''')
    db.execute('''CREATE TABLE IF NOT EXISTS shared_bank_items (
        uid INTEGER PRIMARY KEY, account_id INTEGER NOT NULL CHECK(account_id>0),
        slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 47), item_json TEXT NOT NULL,
        UNIQUE(account_id,slot))''')


def account_for(db,owner):
    character_uid(owner)
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='character_owners'").fetchone():
        row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
        if row is None:raise ValueError('Unknown bank owner')
        return row[0]
    if owner==1001:return 1
    raise ValueError('Unknown bank account')


def container(db,owner,group):
    if group==8:
        account_for(db,owner)
        return 'private_bank_items','owner',owner
    if group==16:return 'shared_bank_items','account_id',account_for(db,owner)
    raise ValueError('Unknown bank container')


def expire(db,owner):
    due=[e for e in load(db,owner,include_expired=True)+load(db,owner,include_expired=True,group=16) if expired(e['item'])]
    for entry in due:
        table,key,identity=container(db,owner,entry['position'][0])
        db.execute(f'DELETE FROM {table} WHERE uid=? AND {key}=?',(entry['item']['uid'],identity))
    return due


def remove_due(path,owner):
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        # No expired owned instance means no write transaction is needed.
        # Release the probe snapshot before obtaining the writer reservation;
        # expire() reloads both containers after that reservation succeeds.
        db.execute('BEGIN')
        if not any(expired(e['item']) for e in load(db,owner,include_expired=True)+load(db,owner,include_expired=True,group=16)):return []
        db.rollback()
        db.execute('BEGIN IMMEDIATE');due=expire(db,owner)
        if not due:return []
        # The original 105 reader also accepts bank wrapper positions.
        return [Event(0x201,kind=0x105,payload=transfer_ack([(e['position'],None) for e in due]))]


def capacity(db,owner,group=8):
    _,_,identity=container(db,owner,group)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='bank_capacities'").fetchone():return 8
    row=db.execute('SELECT capacity FROM bank_capacities WHERE bank_group=? AND identity=?',(group,identity)).fetchone()
    value=row[0] if row else 8
    if value not in TIERS:raise ValueError('Invalid persisted bank tier')
    return value


def load(db,owner,include_expired=False,group=8):
    owner=character_uid(owner)
    table,key,identity=container(db,owner,group)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'",(table,)).fetchone():return []
    entries=[]
    for uid,slot,raw in db.execute(f'SELECT uid,slot,item_json FROM {table} WHERE {key}=? ORDER BY slot',(identity,)):
        stored=json.loads(raw)
        from els_server.domain.cartridge_selection_box import BOX,read_existing_box
        from els_server.storage.equipment_chip_reset_history import hydrate
        item=hydrate(db,validate_item(read_existing_box(stored) if type(stored) is dict and stored.get('template')==BOX else stored))
        if item['uid']!=uid or item['group']==9 or slot>=capacity(db,owner,group):raise ValueError('Bank persisted instance/slot mismatch')
        if db.execute('SELECT 1 FROM inventory_items WHERE uid=?',(uid,)).fetchone():raise ValueError('Bank instance is also in a bag')
        if include_expired or not expired(item):entries.append(dict(position=(group,slot),item=item))
    return entries


def snapshot(path,owner):
    with closing(sqlite3.connect(path,timeout=10)) as db:
        db.execute('BEGIN')
        return dict(bank_capacities={g:capacity(db,owner,g) for g in (8,16)},bank_items=load(db,owner)+load(db,owner,group=16))


def put(db,owner,position,item):
    if position[0] in (8,16):
        from els_server.storage.equipment_chip_reset_history import hydrate,legacy
        item=legacy(hydrate(db,validate_item(item)))
        ensure(db)
        table,key,identity=container(db,owner,position[0])
        if db.execute('SELECT 1 FROM inventory_items WHERE uid=?',(item['uid'],)).fetchone():raise ValueError('Bank UID remains in inventory')
        other='shared_bank_items' if position[0]==8 else 'private_bank_items'
        if db.execute(f'SELECT 1 FROM {other} WHERE uid=?',(item['uid'],)).fetchone():raise ValueError('Bank UID remains in another container')
        db.execute(f'INSERT INTO {table} VALUES (?,?,?,?)',
            (item['uid'],identity,position[1],json.dumps(validate_item(item),sort_keys=True)))
    else:
        moved=dict(item,group=position[0],slot=position[1])
        from els_server.domain.cartridge_selection_box import BOX,relocate_existing_box
        if item['template']==BOX:moved=relocate_existing_box(item,moved)
        insert(db,owner,moved)


def delete(db,owner,position,item):
    if position[0] in (8,16):
        table,key,identity=container(db,owner,position[0])
        if db.execute(f'DELETE FROM {table} WHERE uid=? AND {key}=?',(item['uid'],identity)).rowcount!=1:
            raise ValueError('Bank instance owner changed')
    else:remove(db,owner,item)


def current_transfer_changes(db,operation,owner,points,positions):
    """Refresh only committed affected UIDs still owned by this character/account."""
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(owner,0x551):raise ValueError('Bank receipt owner or kind mismatch')
    try:
        before,after=(json.loads(raw) for raw in row[2:])
        if not isinstance(before,list) or not isinstance(after,list):raise ValueError('Bank receipt arrays')
        affected=set()
        for entry in before+after:
            if not isinstance(entry,dict):raise ValueError('Bank receipt entry')
            # Bank wrappers retain their original bag group in item_json;
            # only the wrapper position identifies the historic bank slot.
            if 'position' in entry:
                point=tuple(entry['position']);item=entry['item']
            else:point=(entry['group'],entry['slot']);item=entry
            if point in points:
                uid=item['uid']
                if type(uid) is not int or not 0<uid<2**63:raise ValueError('Bank receipt UID')
                affected.add(uid)
    except (TypeError,KeyError,json.JSONDecodeError) as exc:
        raise ValueError('Bank receipt history format') from exc
    ordered=list(dict.fromkeys([*points,*[p for p,item in positions.items() if item['uid'] in affected]]))
    return [(p,positions.get(p)) for p in ordered]


def transfer(path,owner,payload,operation):
    source,destination,quantity,context,template=transfer_request(payload)
    owner,digest=_identity(owner,0x551,payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        old=_previous(db,operation,digest)
        expire(db,owner)
        before=load_items(db,owner);bank=load(db,owner)+load(db,owner,group=16)
        positions={(i['group'],i['slot']):i for i in before}
        positions.update((tuple(e['position']),e['item']) for e in bank)
        if old is not None:return transfer_ack(current_transfer_changes(db,operation,owner,old,positions))
        limits=allowances(db,owner);limits.update({g:capacity(db,owner,g) for g in (8,16)})
        if any(g not in limits or s>=limits[g] for g,s in (source,destination)):
            raise ValueError('Unowned bank/bag position')
        first,second=positions.get(source),positions.get(destination)
        if first is None or first['template']!=template or quantity>first['count']:
            raise ValueError('Bank transfer item/quantity mismatch')
        # Context never selects a SQL owner. Accept only zero or an identity
        # already owned by this connection, regardless of caller variation.
        if context not in (0,owner,first['uid']):raise ValueError('Foreign bank transfer context')
        for item in (first,second):
            if item:require_current(item)
        if destination[0] in (8,16):require_storable(first,destination[0])
        if second and source[0] in (8,16):require_storable(second,source[0])
        if destination[0] not in (8,16) and destination[0]!=TEMPLATE_BAG_GROUPS[first['template']]:
            raise ValueError('Bank withdrawal has wrong item tab')
        if second and source[0] not in (8,16) and source[0]!=TEMPLATE_BAG_GROUPS[second['template']]:
            raise ValueError('Bank swap has wrong item tab')
        from els_server.domain.cartridge_selection_box import BOX,relocate_existing_box
        if first['template']==BOX and quantity!=first['count']:
            raise ValueError('Cartridge box bank move retains whole original count')
        # Stack only identical complete states, excluding UID and position.
        signature=lambda i:{k:v for k,v in i.items() if k not in ('uid','group','slot','count')}
        merging=second is not None and signature(first)==signature(second) and TEMPLATE_MAX_STACKS[template]>1
        if merging and second['count']+quantity>TEMPLATE_MAX_STACKS[template]:raise ValueError('Bank stack overflow')
        if second and not merging and quantity!=first['count']:raise ValueError('Partial bank transfer cannot swap')
        delete(db,owner,source,first)
        if second:delete(db,owner,destination,second)
        remaining=dict(first,count=first['count']-quantity) if quantity<first['count'] else None
        if merging:moved=dict(second,count=second['count']+quantity)
        else:moved=dict(first,count=quantity,uid=next_uid(db) if remaining else first['uid'])
        if first['template']==BOX:moved=relocate_existing_box(first,moved)
        swapped=second if second and not merging else remaining
        if swapped:put(db,owner,source,swapped)
        put(db,owner,destination,moved)
        after=load_items(db,owner);bank_after=load(db,owner)+load(db,owner,group=16)
        updated={(i['group'],i['slot']):i for i in after}
        updated.update((tuple(e['position']),e['item']) for e in bank_after)
        changes=[(p,updated.get(p)) for p in (source,destination)]
        wire=transfer_ack(changes)
        _commit(db,operation,digest,owner,0x551,[source,destination],before+bank,after+bank_after)
        return wire


def sort(path,owner,payload,operation):
    if payload not in (struct.pack('>i',8),struct.pack('>i',16)):raise ValueError('Unsupported bank sort group')
    group=struct.unpack('>i',payload)[0]
    owner,digest=_identity(owner,0x372,payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');require_active_character(db,owner);old=_previous(db,operation,digest)
        expire(db,owner)
        before=load(db,owner,group=group)
        if old is not None:return sort_ack(group,[e['item']['uid'] for e in before])
        # The response explicitly supplies ordering; never sort the live client
        # object's temporary slot numbers or merge dissimilar instance states.
        after=[dict(position=(group,n),item=e['item']) for n,e in enumerate(sorted(before,key=lambda e:(e['item']['template'],e['item']['uid'])))]
        ensure(db);table,key,identity=container(db,owner,group)
        db.execute(f'DELETE FROM {table} WHERE {key}=?',(identity,))
        for entry in after:put(db,owner,entry['position'],entry['item'])
        # 1987260 removes UIDs absent from this ordered vector; 1985130 then
        # writes its absolute slot indices. Re-adding rows would mark them NEW.
        wire=sort_ack(group,[e['item']['uid'] for e in after])
        _commit(db,operation,digest,owner,0x372,[(group,n) for n in range(capacity(db,owner,group))],before,after)
        return wire


def quote(path,owner,group):
    with closing(sqlite3.connect(path,timeout=10)) as db:
        db.execute('BEGIN');current=capacity(db,owner,group)
        return current,expansion_cost(group,current)


def set_capacity(db,owner,group,value):
    if not db.in_transaction or value not in TIERS or value<=capacity(db,owner,group):
        raise ValueError('Invalid bank membership upgrade')
    db.execute('''CREATE TABLE IF NOT EXISTS bank_capacities (
        bank_group INTEGER NOT NULL CHECK(bank_group IN (8,16)),
        identity INTEGER NOT NULL,capacity INTEGER NOT NULL CHECK(capacity IN (8,16,24,32,40,48)),
        PRIMARY KEY(bank_group,identity))''')
    identity=container(db,owner,group)[2]
    db.execute('INSERT INTO bank_capacities VALUES (?,?,?) ON CONFLICT(bank_group,identity) DO UPDATE SET capacity=excluded.capacity',(group,identity,value))


def expand(path,owner,group,payload,operation,expected=None):
    from els_server.protocol.bank_messages import expansion_ack
    from els_server.storage.npc_trade import balances,charge
    if payload or group not in (8,16):raise ValueError('Invalid bank expansion request')
    kind=0x475 if group==8 else 0x54d
    owner,digest=_identity(owner,kind,payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');require_active_character(db,owner);account_for(db,owner)
        old=_previous(db,operation,digest);balance=balances(db,owner)
        if old is not None:return expansion_ack(group,balance['ed'])
        current=capacity(db,owner,group);cost=expansion_cost(group,current)
        if expected!=(current,cost):raise ValueError('Bank expansion quote is missing or changed')
        ed=charge(db,owner,balance,cost)
        set_capacity(db,owner,group,current+8)
        wire=expansion_ack(group,ed,8)
        _commit(db,operation,digest,owner,kind,[],[dict(group=group,capacity=current)],[dict(group=group,capacity=current+8)])
        return wire


def contents(path,owner,group):
    from els_server.protocol.bank_messages import contents_ack
    from els_server.storage.bank_money import balance as money_balance
    with closing(sqlite3.connect(path,timeout=10)) as db:
        db.execute('BEGIN');entries=load(db,owner,group=group)
        # Clear positions before restoring the map, including slots from
        # which a sibling character withdrew while this connection was away.
        empty=[((group,n),None) for n in range(capacity(db,owner,group))]
        return [Event(0x201,kind=0x105,payload=transfer_ack(empty)),
            Event(0x201,kind=0x26b if group==8 else 0x550,payload=contents_ack(entries,ed=money_balance(db,owner)[0] if group==16 else None))]
