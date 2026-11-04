"""Account-owned heater points and bag, sharing the existing item transaction."""
import json,sqlite3,struct
from contextlib import closing
from els_server.domain import modern_ice as rules
from els_server.protocol import modern_ice_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner

def authorize(db,owner,account_id,prepare):
    if not callable(prepare):raise ValueError('Current selected ice actor required')
    prepare(db);require_active_character(db,owner);require_owner(db,owner,account_id)

def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS modern_ice_points (account_id INTEGER PRIMARY KEY,points INTEGER NOT NULL CHECK(points BETWEEN 0 AND 10000))')
    db.execute('CREATE TABLE IF NOT EXISTS modern_ice_bag (uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL,template INTEGER NOT NULL,metadata INTEGER NOT NULL,count INTEGER NOT NULL CHECK(count>0),bag_group INTEGER NOT NULL,slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 32767),UNIQUE(account_id,slot))')
    db.execute('CREATE INDEX IF NOT EXISTS modern_ice_bag_account ON modern_ice_bag(account_id,uid)')

def exists(db,table):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()is not None
def point_balance(db,account_id):
    row=db.execute('SELECT points FROM modern_ice_points WHERE account_id=?',(account_id,)).fetchone()if exists(db,'modern_ice_points')else None
    return row[0]if row else 0

def bag_items(db,account_id):
    if not exists(db,'modern_ice_bag'):return []
    return [dict(zip(('uid','template','metadata','count','group','slot'),r))for r in db.execute('SELECT uid,template,metadata,count,bag_group,slot FROM modern_ice_bag WHERE account_id=? ORDER BY slot',(account_id,))]

def add(db,account_id,template,quantity):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    from els_server.domain.acquisition_policy import can_acquire
    if not can_acquire(template):raise ValueError('Ice reward acquisition not allowed')
    ensure(db);stack=TEMPLATE_MAX_STACKS[template];metadata=VERIFIED_TEMPLATES[template];group=TEMPLATE_BAG_GROUPS[template]
    for uid,count in db.execute('SELECT uid,count FROM modern_ice_bag WHERE account_id=? AND template=? AND count<? ORDER BY uid',(account_id,template,stack)).fetchall():
        delta=min(quantity,stack-count);db.execute('UPDATE modern_ice_bag SET count=count+? WHERE uid=?',(delta,uid));quantity-=delta
        if not quantity:return
    while quantity:
        uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
        if not 0<uid<2**63-1:raise ValueError('Ice bag UID overflow')
        count=min(quantity,stack);quantity-=count
        occupied={row[0]for row in db.execute('SELECT slot FROM modern_ice_bag WHERE account_id=?',(account_id,))}
        slot=next((i for i in range(32768)if i not in occupied),None)
        if slot is None:raise ValueError('Ice bag native slot range exhausted')
        db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(uid+1,))
        db.execute('INSERT INTO modern_ice_bag VALUES(?,?,?,?,?,?,?)',(uid,account_id,template,metadata,count,group,slot))

def accrue(db,account_id,machine,template):
    ensure(db);points=min(10000,point_balance(db,account_id)+rules.points_earned(machine,template))
    db.execute('INSERT INTO modern_ice_points VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET points=excluded.points',(account_id,points))
    return points

def snapshot_current(db,owner,account_id,prepare,*,initial=False,bag=True):
    authorize(db,owner,account_id,prepare)
    events=(wire.bag_events(0xbd2 if initial else 0xbd5,bag_items(db,account_id))if bag else[])+[wire.points(point_balance(db,account_id),initial=initial)]
    for event in events:encode_event(event)
    return events

def snapshot(path,owner,account_id,prepare,*,initial=False,bag=True):
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN')
        return snapshot_current(db,owner,account_id,prepare,initial=initial,bag=bag)

def _identity(owner,account_id,kind,payload,operation):
    from els_server.storage.inventory_actions import _identity
    _,digest=_identity(owner,kind,struct.pack('>Q',account_id)+payload,operation)
    return digest

def _previous(db,operation,digest):
    db.execute('CREATE TABLE IF NOT EXISTS modern_ice_receipts(operation TEXT PRIMARY KEY,digest TEXT NOT NULL,kind INTEGER NOT NULL,owner INTEGER NOT NULL,account_id INTEGER NOT NULL,positions TEXT NOT NULL)')
    row=db.execute('SELECT digest,positions FROM modern_ice_receipts WHERE operation=?',(operation,)).fetchone()
    if row and row[0]!=digest:raise ValueError('Conflicting ice request replay')
    return json.loads(row[1])if row else None

def _save(db,operation,digest,kind,owner,account_id,positions):
    db.execute('INSERT INTO modern_ice_receipts VALUES(?,?,?,?,?,?)',(operation,digest,kind,owner,account_id,json.dumps(positions)))

def claim(path,owner,account_id,payload,operation,prepare):
    machine,template=wire.claim_request(payload);config=rules.machines().get(machine)
    if config is None or template not in config['boxes']:raise ValueError('Ice point reward outside this season')
    # Keep the current locally approved storefront scope, including historical
    # series intentionally sold here; original retail sale dates are not mixed in.
    from els_server.domain.inventory_items import native_ice_catalog
    if config['paid']not in {r['template']for r in native_ice_catalog()['offers']}:raise ValueError('Ice redemption season unavailable')
    digest=_identity(owner,account_id,0xbda,payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE');authorize(db,owner,account_id,prepare);ensure(db)
        from els_server.storage.character_schema import stored_character_type
        from els_server.domain.ice_rules import series_pools
        if machine not in series_pools(stored_character_type(db,owner)):raise ValueError('Ice redemption character is not supported')
        old=_previous(db,operation,digest)
        if old is None:
            if point_balance(db,account_id)<10000:raise ValueError('Insufficient ice points')
            from els_server.storage.inventory_state import ensure_inventory
            ensure_inventory(db);add(db,account_id,template,1)
            db.execute('UPDATE modern_ice_points SET points=points-10000 WHERE account_id=?',(account_id,))
            _save(db,operation,digest,0xbda,owner,account_id,[])
        points=point_balance(db,account_id)
        events=[wire.claim(template,points)]+wire.bag_events(0xbd5,bag_items(db,account_id))+[wire.points(points)]
        for event in events:encode_event(event)
        authorize(db,owner,account_id,prepare)
        return events

def withdraw(path,owner,account_id,payload,operation,prepare):
    requested=wire.withdraw_request(payload);digest=_identity(owner,account_id,0xbd4,payload,operation)
    from els_server.storage.inventory_state import load_items,grant_items
    from els_server.storage.inventory_management import _updates
    from els_server.storage.npc_trade import balances
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE');authorize(db,owner,account_id,prepare);ensure(db)
        old=_previous(db,operation,digest)
        if old is None:
            items={i['uid']:i for i in bag_items(db,account_id)};plan=[]
            for uid,count in requested:
                item=items.get(uid)
                if item is None or count>item['count']:raise ValueError('Ice bag owned quantity required')
                plan.append(dict(template=item['template'],metadata=item['metadata'],group=item['group'],quantity=count))
                if count==item['count']:db.execute('DELETE FROM modern_ice_bag WHERE uid=? AND account_id=?',(uid,account_id))
                else:db.execute('UPDATE modern_ice_bag SET count=count-? WHERE uid=? AND account_id=?',(count,uid,account_id))
            before=load_items(db,owner);balance=balances(db,owner)
            if balance['revision']>=2**63-1:raise ValueError('Ice bag inventory revision overflow')
            grants=grant_items(db,plan,owner);positions=sorted({(i['group'],i['slot'])for i in grants})
            after=load_items(db,owner)
            from els_server.storage.inventory_actions import _commit
            _commit(db,operation,digest,owner,0xbd4,positions,before,after)
            _save(db,operation,digest,0xbd4,owner,account_id,dict(inventory=positions,bag=[(uid,items[uid]['slot'])for uid,_ in requested]))
            db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
            bag_history=[(uid,items[uid]['slot'])for uid,_ in requested]
        else:after=load_items(db,owner)
        current={(i['group'],i['slot']):i for i in after}
        if old is not None:
            from els_server.storage.equipment_receipt_state import current_changes
            changes=current_changes(db,operation,owner,0xbd4,[tuple(p)for p in old['inventory']],after)
            bag_history=old['bag']
        else:changes=[(p,current.get(p))for p in positions]
        current_bag=bag_items(db,account_id);by_slot={i['slot']:i for i in current_bag}
        affected={uid for uid,_ in bag_history};slots={slot for _,slot in bag_history}|{i['slot']for i in current_bag if i['uid']in affected}
        events=_updates(changes)+wire.bag_change_events(0xbd4,[(p,by_slot.get(p))for p in sorted(slots)])
        for event in events:encode_event(event)
        authorize(db,owner,account_id,prepare)
        return events

def sort_bag(path,owner,account_id,prepare):
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE');authorize(db,owner,account_id,prepare)
        before=bag_items(db,account_id);rows=sorted(before,key=lambda i:(i['template'],i['uid']))
        if rows:
            db.execute('DELETE FROM modern_ice_bag WHERE account_id=?',(account_id,))
            for slot,item in enumerate(rows):
                item['slot']=slot
                db.execute('INSERT INTO modern_ice_bag VALUES(?,?,?,?,?,?,?)',(item['uid'],account_id,item['template'],item['metadata'],item['count'],item['group'],slot))
        # Clear old locations, publish the same instances at sorted locations,
        # then finish the native BD7 wait. No giant all-items frame is required.
        events=(wire.bag_change_events(0xbd5,[(i['slot'],None)for i in before])+wire.bag_events(0xbd5,rows)
            if rows else[])+[wire.bag(0xbd7),wire.points(point_balance(db,account_id))]
        for event in events:encode_event(event)
        authorize(db,owner,account_id,prepare)
        return events

def open_box(path,owner,template,payload,operation,*,account_id,prepare):
    from els_server.protocol.ice_messages import use_request
    from els_server.protocol.cube_messages import result
    from els_server.storage.inventory_actions import _identity as identity,_previous as previous,_commit
    from els_server.storage.inventory_management import _updates
    from els_server.storage.inventory_state import load_items,grant_items
    from els_server.storage.equipment_receipt_state import current_changes
    from els_server.storage.item_instances import remove
    from els_server.storage.npc_trade import balances
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    request=use_request(payload)
    if request.choices or request.option not in(0,1) or any(v not in(0,1)for v in(request.flag1,request.flag2,request.flag3)):raise ValueError('Ice cube native use mode')
    owner,digest=identity(owner,0x196,struct.pack('>i',template)+payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE');authorize(db,owner,account_id,prepare)
        old=previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        if old is not None:
            events=_updates(current_changes(db,operation,owner,0x196,old,before))+result(balance['ed'])
        else:
            item=next((i for i in before if i['uid']==request.uid),None)
            if item is None or item['template']!=template or item['group']!=4:raise ValueError('Owned ice cube required')
            require_current(item);require_unlocked(item)
            from els_server.storage.character_schema import stored_character_type
            role=stored_character_type(db,owner)
            from els_server.storage.luciel_state import active_state
            minor=active_state(db,owner)['active_unit']if role==10 else 0
            if request.flag2!=minor:raise ValueError('Ice cube opening active character mismatch')
            output=rules.output_for(template,role,minor)
            if balance['revision']>=2**63-1:raise ValueError('Ice cube inventory revision overflow')
            if item['count']==1:remove(db,owner,item)
            else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
            t=output['template'];grants=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1)],owner)
            after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
            positions=sorted({(item['group'],item['slot']),*[(i['group'],i['slot'])for i in grants]})
            events=result(balance['ed'],[(p,current.get(p))for p in positions],[(t,1)])
            _commit(db,operation,digest,owner,0x196,positions,before,after)
            db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        for event in events:encode_event(event)
        authorize(db,owner,account_id,prepare)
        return events
