"""Pet entitlements, automatic consumable settings and owned accessories."""
import hashlib,json,secrets,sqlite3,struct
from contextlib import closing
from els_server.domain.pet_support import PRODUCTS,catalog
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.protocol import pet_support_messages as wire
from els_server.protocol.career_messages import use_ack
from els_server.protocol.companion_messages import event
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.companion_receipt_inventory import current_changes,delta

DEFAULT=dict(automatic=0,upgrade=0,enabled=1,hp=50,mp=50,hp_seconds=0,mp_seconds=0,hp_binding=0,mp_binding=0,cheer=40,cheer_a=0,cheer_b=0)

def ensure(db):
    from els_server.storage.companion_state import ensure as companions
    companions(db)
    db.execute('CREATE TABLE IF NOT EXISTS pet_entitlements (owner INTEGER NOT NULL,pet INTEGER PRIMARY KEY,pickup INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS pet_automatic (owner INTEGER PRIMARY KEY,state TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS pet_accessories (owner INTEGER NOT NULL,pet INTEGER NOT NULL,slot INTEGER NOT NULL,item_uid INTEGER NOT NULL UNIQUE,item TEXT NOT NULL,socket INTEGER NOT NULL,PRIMARY KEY(pet,slot))')
    db.execute('CREATE TABLE IF NOT EXISTS pet_support_receipts (owner INTEGER NOT NULL,operation TEXT NOT NULL,digest TEXT NOT NULL,context TEXT NOT NULL,PRIMARY KEY(owner,operation))')

def attach(db,owner,pets,*,now=None):
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='pet_entitlements'").fetchone():
        pickups=dict(db.execute('SELECT pet,pickup FROM pet_entitlements WHERE owner=?',(owner,)))
        for p in pets:
            if p['kind']=='pet':
                from els_server.storage.pet_support_periods import period,active
                deadline=period(db,owner,'pickup',p['uid'])
                p['pickup']=bool(pickups.get(p['uid'],0))and active(deadline,now)
                if deadline is not None:p['pickup_expires_at']=deadline
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='pet_accessories'").fetchone():
        equipment={}
        for pet,slot,item,socket in db.execute('SELECT pet,slot,item,socket FROM pet_accessories WHERE owner=?',(owner,)):
            equipment.setdefault(pet,{})[slot]=dict(template=json.loads(item)['template'],socket=socket)
        for p in pets:
            if p['kind']=='pet':p['equipment']=equipment.get(p['uid'],{})

def automatic(db,owner,*,now=None):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='pet_automatic'").fetchone():return dict(DEFAULT)
    row=db.execute('SELECT state FROM pet_automatic WHERE owner=?',(owner,)).fetchone()
    saved=json.loads(row[0]) if row else {}
    state={key:saved.get(key,value) for key,value in DEFAULT.items()}
    from els_server.storage.pet_support_periods import period,active
    deadline=period(db,owner,'automatic',0)
    state['automatic_expires_at']=deadline or 0
    if deadline is not None and not active(deadline,now):state['automatic']=0
    return state

def save_automatic(db,owner,state):
    db.execute('INSERT INTO pet_automatic VALUES (?,?) ON CONFLICT(owner) DO UPDATE SET state=excluded.state',(owner,json.dumps(state,sort_keys=True)))

def initialization(path,owner):
    with closing(sqlite3.connect(path)) as db:return wire.settings(automatic(db,owner))

def owned_pet(db,owner,uid,*,now=None):
    from els_server.storage.companion_state import rows
    pet=next((p for p in rows(db,owner,'pet') if p['uid']==uid),None)
    if pet is None:raise ValueError('Owned pet required')
    from els_server.storage.pet_expedition import require_available
    require_available(db,owner,uid)
    from els_server.storage.boosting_2026_limited_pet import require_current
    require_current(pet)
    from els_server.storage.pet_support_periods import period,active
    deadline=period(db,owner,'pickup',uid)
    if deadline is not None:
        pet['pickup_expires_at']=deadline
        # Preserve the stored raw pickup bit even if the ordinary rows() read
        # used a different current clock; only this explicit instant qualifies.
        raw=db.execute('SELECT pickup FROM pet_entitlements WHERE owner=?AND pet=?',(owner,uid)).fetchone()
        pet['pickup']=bool(raw and raw[0])and active(deadline,now)
    return pet

def consume(db,owner,item):
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    require_current(item);require_unlocked(item)
    remaining=dict(item,count=item['count']-1) if item['count']>1 else None
    if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],owner))
    else:
        from els_server.storage.item_instances import remove
        remove(db,owner,item)
    return remaining

def handle(path,owner,kind,payload,operation,*,randbelow=secrets.randbelow,now=None,account_id=None,prepare=None):
    owner=character_uid(owner)
    if not isinstance(operation,str) or not 1<=len(operation)<=160:raise ValueError('Pet support operation identity')
    digest=hashlib.sha256(struct.pack('>I',kind)+payload).hexdigest()
    def timed_authority(db):
        if not callable(prepare):raise ValueError('Current timed pet support actor callback required')
        prepare(db)
        from els_server.storage.item_actor import require_active_character
        from els_server.storage.profession_state import require_owner
        require_active_character(db,owner);require_owner(db,owner,account_id)
        return True
    with closing(sqlite3.connect(path,timeout=10)) as db:
        try:
            db.execute('BEGIN IMMEDIATE');ensure(db)
            prior=db.execute('SELECT digest,context FROM pet_support_receipts WHERE owner=? AND operation=?',(owner,operation)).fetchone()
            if prior:
                if prior[0]!=digest:raise ValueError('Conflicting pet support retry')
                context=json.loads(prior[1])
                if context.get('timed_support'):timed_authority(db)
                answers=reconcile(db,owner,context,now=now)
                for answer in answers:encode_event(answer)
                if context.get('timed_support'):timed_authority(db)
                db.commit();return answers
            context=dict(kind=kind,pet=0)
            if kind==0x219:
                item_uid,pet_uid=wire.use_request(payload)
                item=next((i for i in load_items(db,owner) if i['uid']==item_uid),None)
                if item is None or item['template'] not in PRODUCTS:
                    db.rollback();return None
                if item['group']!=4:raise ValueError('Pet coupon outside owned bag')
                context['item']=dict(item)
                from els_server.storage import pet_support_periods as periods
                timed=item['template']in periods.PRODUCTS
                if timed:periods.validate_product(item['template']);timed_authority(db);context['timed_support']=True
                product=PRODUCTS[item['template']];state=automatic(db,owner,now=now)
                if product=='pickup':
                    pet=owned_pet(db,owner,pet_uid,now=now)
                    previous=periods.period(db,owner,'pickup',pet_uid)
                    if pet.get('pickup')and previous is None:raise ValueError('Pet already has permanent pickup')
                    if timed:periods.renew(db,owner,'pickup',pet_uid,periods.PRODUCTS[item['template']][1],operation,now=now)
                    else:periods.permanent(db,owner,'pickup',pet_uid)
                    db.execute('INSERT INTO pet_entitlements VALUES (?,?,1) ON CONFLICT(pet) DO UPDATE SET pickup=1',(owner,pet_uid))
                    context['pet']=pet_uid
                else:
                    if pet_uid:owned_pet(db,owner,pet_uid)
                    previous=periods.period(db,owner,'automatic',0)
                    if state[product]and(product!='automatic'or previous is None):raise ValueError('Pet automatic entitlement already unlocked')
                    if product=='upgrade'and(not state['automatic']or previous is not None):raise ValueError('Permanent automatic slot must be expanded first')
                    if not db.execute("SELECT 1 FROM companions WHERE owner=? AND kind='pet'",(owner,)).fetchone():raise ValueError('An activated pet is required')
                    if product=='automatic':
                        if timed:periods.renew(db,owner,'automatic',0,periods.PRODUCTS[item['template']][1],operation,now=now)
                        else:periods.permanent(db,owner,'automatic',0)
                    state[product]=1;state.pop('automatic_expires_at',None);save_automatic(db,owner,state)
                    state=automatic(db,owner,now=now)
                remaining=consume(db,owner,item)
                ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0]
                answers=[use_ack([((item['group'],item['slot']),remaining)],item['template'],ed)]
                answers+=([wire.pet_update(owned_pet(db,owner,pet_uid,now=now))] if product=='pickup' else [wire.settings(state,0xb3b)])
            elif kind==0x8c7:
                if len(payload)!=20:raise ValueError('Pet equipment request length')
                pet_uid,slot,item_uid=struct.unpack('>QiQ',payload)
                pet=owned_pet(db,owner,pet_uid)
                if slot not in (1,2) or not 0<item_uid<2**63:raise ValueError('Pet equipment slot/item; native gems cannot be removed')
                item=next((i for i in load_items(db,owner) if i['uid']==item_uid),None)
                if item is None or item['template'] not in catalog()['equipment'] or item['group']!=21 or item['count']!=1:raise ValueError('Owned pet accessory required')
                from els_server.domain.pet_accessory_rules import roll
                socket=roll(item['template'],randbelow)
                remaining=consume(db,owner,item)
                if remaining is not None:raise ValueError('Pet accessory cannot stack')
                db.execute('INSERT INTO pet_accessories VALUES (?,?,?,?,?,?) ON CONFLICT(pet,slot) DO UPDATE SET item_uid=excluded.item_uid,item=excluded.item,socket=excluded.socket',(owner,pet_uid,slot,item_uid,json.dumps(item,sort_keys=True),socket))
                context.update(pet=pet_uid,item=dict(item))
                answers=[wire.equipment_ack(owned_pet(db,owner,pet_uid),removed=item)]
            elif kind==0x661:
                state=automatic(db,owner);request=wire.settings_request(payload)
                if not state['automatic']:raise ValueError('Pet automatic slot is locked')
                if not state['upgrade'] and max(request['hp'],request['mp'])>90:raise ValueError('Automatic threshold requires upgrade')
                if not state['upgrade'] and (request['enabled']!=1 or request['hp_seconds'] or request['mp_seconds']):raise ValueError('Automatic timers require upgrade')
                state.update(request);save_automatic(db,owner,state);answers=[wire.settings(state)]
            elif kind==0x8a1:
                if len(payload)!=24 or struct.unpack_from('>iI',payload)!=(2,2):raise ValueError('Automatic binding map length/type')
                entries=dict(struct.unpack_from('>ii',payload,8+8*n) for n in range(2))
                if set(entries)!={0,1} or any(v<0 for v in entries.values()):raise ValueError('Automatic binding keys')
                state=automatic(db,owner)
                if not state['automatic']:raise ValueError('Pet automatic slot is locked')
                from els_server.domain.quick_bindings import item_binding
                from els_server.domain.consumables import require_usable
                level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]
                candidates={}
                for i in load_items(db,owner):
                    if i['group']==6:
                        try:meta=require_usable(i['template'],level,automatic=True)
                        except ValueError:continue
                        candidates[item_binding(i['template'])]=meta
                for slot,key in ((0,'hp_binding'),(1,'mp_binding')):
                    binding=entries[slot]
                    if binding and binding not in candidates and binding!=state[key]:raise ValueError('Unowned or unsupported automatic consumable')
                    if binding in candidates:
                        effects={struct.unpack_from('<I',bytes.fromhex(raw))[0] for raw in candidates[binding]['effects']}
                        if not effects.intersection((1,13) if slot==0 else (2,)):raise ValueError('Automatic consumable does not restore the selected resource')
                    state[key]=binding
                save_automatic(db,owner,state);answers=[bindings_ack(state)]
            elif kind==0x2fb:
                from els_server.protocol.companion_messages import uid_request
                from els_server.storage.pet_progression import evolve
                from els_server.protocol.pet_progression_messages import refresh
                pet=evolve(db,owner,uid_request(payload));answers=[wire.pet_update(pet)];context['pet']=pet['uid']
                if db.execute('SELECT 1 FROM companion_active WHERE owner=? AND pet=?',(owner,pet['uid'])).fetchone():answers.append(refresh(owner,pet))
            else:raise ValueError('Unknown pet support operation')
            db.execute('INSERT INTO pet_support_receipts VALUES (?,?,?,?)',(owner,operation,digest,json.dumps(context)))
            db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
            for answer in answers:encode_event(answer)
            if context.get('timed_support'):timed_authority(db)
            db.commit();return answers
        except BaseException:db.rollback();raise

def reconcile(db,owner,context,*,now=None):
    kind=context['kind']
    old=context.get('item');items=load_items(db,owner) if old else []
    if kind==0x219:
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(owner,)).fetchone()[0]
        changes=current_changes(items,old)
        return [use_ack(changes,ed=ed)]+([wire.pet_update(owned_pet(db,owner,context['pet'],now=now))] if context['pet'] else [wire.settings(automatic(db,owner,now=now),0xb3b)])
    if kind==0x8c7:return [wire.equipment_ack(owned_pet(db,owner,context['pet']),**delta(items,old))]
    if kind==0x8a1:return [bindings_ack(automatic(db,owner))]
    return [wire.settings(automatic(db,owner))] if kind==0x661 else [wire.pet_update(owned_pet(db,owner,context['pet']))]

def binding_map(state):return struct.pack('>Iiiii',2,0,state['hp_binding'],1,state['mp_binding'])
def bindings_ack(state=None,result=0):return event(0x8a2,struct.pack('>ii',result,2)+binding_map(state or DEFAULT))

def automatic_binding_map(path,owner):
    with closing(sqlite3.connect(path)) as db:return binding_map(automatic(db,owner))

def active_effects(db,owner):
    from els_server.domain.pet_accessory_rules import effects
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_active'").fetchone():return {}
    row=db.execute('SELECT pet FROM companion_active WHERE owner=?',(owner,)).fetchone()
    if not row or not row[0]:return {}
    from els_server.storage.boosting_2026_limited_pet import ExpiredLimitedPet
    try:return effects(owned_pet(db,owner,row[0]).get('equipment',{}))
    except ExpiredLimitedPet:return {}


def remote_pickup_enabled(path,owner):
    """Only the currently summoned, owned pet can provide pickup entitlement."""
    with closing(sqlite3.connect(path)) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'companion_active','companions','pet_entitlements'}<=tables:return False
        row=db.execute("SELECT a.pet FROM companion_active a JOIN companions p ON p.uid=a.pet AND p.owner=a.owner AND p.kind='pet' JOIN pet_entitlements e ON e.pet=p.uid AND e.owner=p.owner WHERE a.owner=? AND e.pickup=1",(character_uid(owner),)).fetchone()
        if row is None:return False
        from els_server.storage.boosting_2026_limited_pet import ExpiredLimitedPet
        try:return bool(owned_pet(db,owner,row[0]).get('pickup'))
        except ExpiredLimitedPet:return False
