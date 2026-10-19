"""Persistent pet feeding/evolution and clear-receipted local battle growth."""
import hashlib,json,sqlite3,struct,time
from contextlib import closing
from els_server.domain.pet_progression import catalog,template,threshold,status
from els_server.protocol import pet_progression_messages as wire
from els_server.storage.character_schema import character_uid
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.companion_receipt_inventory import delta

DEFAULT=dict(step=0,satiety=3840,growth=0,personality={},nutrition=0,hunger_remainder=0)

def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS pet_progression (pet INTEGER PRIMARY KEY,owner INTEGER NOT NULL,state TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS pet_growth_clocks (owner INTEGER PRIMARY KEY,pet INTEGER NOT NULL,accounted_at INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS pet_feeding_receipts (owner INTEGER NOT NULL,operation TEXT NOT NULL,digest TEXT NOT NULL,context TEXT NOT NULL,PRIMARY KEY(owner,operation))')

def attach(db,owner,pets):
    saved={}
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='pet_progression'").fetchone():
        saved={p:json.loads(s) for p,s in db.execute('SELECT pet,state FROM pet_progression WHERE owner=?',(owner,))}
    for pet in pets:
        if pet['kind']=='pet':pet.update({**DEFAULT,**saved.get(pet['uid'],{})})

def save(db,owner,pet):
    state={k:pet[k] for k in DEFAULT}
    if not 0<=state['step']<=template(pet['unit'])['EVOLUTION_ALL_STEP'] or not 0<=state['growth']<=threshold(pet) or not 0<=state['satiety']<=4800 or not 0<=state['nutrition']<=32767:raise ValueError('Pet progression bound')
    db.execute('INSERT INTO pet_progression VALUES (?,?,?) ON CONFLICT(pet) DO UPDATE SET state=excluded.state',(pet['uid'],owner,json.dumps(state,sort_keys=True)))

def clock(db,owner,pet,*,now=None):
    ensure(db);now=int(time.time()) if now is None else now
    if pet:db.execute('INSERT INTO pet_growth_clocks VALUES (?,?,?) ON CONFLICT(owner) DO UPDATE SET pet=excluded.pet,accounted_at=excluded.accounted_at',(owner,pet,now))
    else:db.execute('DELETE FROM pet_growth_clocks WHERE owner=?',(owner,))

def active(db,owner):
    from els_server.storage.companion_state import rows
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_active'").fetchone():raise ValueError('No initialized companion state')
    row=db.execute('SELECT pet FROM companion_active WHERE owner=?',(owner,)).fetchone()
    if not row or not row[0]:raise ValueError('Summoned pet required')
    pet=next((p for p in rows(db,owner,'pet') if p['uid']==row[0]),None)
    if pet is None:raise ValueError('Owned active pet required')
    template(pet['unit']);return pet

def evolve(db,owner,uid):
    from els_server.storage.pet_support import owned_pet
    ensure(db);pet=owned_pet(db,owner,uid)
    if pet['step']>=template(pet['unit'])['EVOLUTION_ALL_STEP'] or pet['growth']<threshold(pet):raise ValueError('Pet is not ready to evolve')
    pet.update(step=pet['step']+1,growth=0);save(db,owner,pet)
    return pet

def clear(db,owner,seconds,*,now=None):
    """Called once, inside the successful dungeon clear reward transaction."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_active'").fetchone():return None
    ensure(db)
    try:pet=active(db,owner)
    except ValueError:return None
    now=int(time.time()) if now is None else now
    prior=db.execute('SELECT pet,accounted_at FROM pet_growth_clocks WHERE owner=?',(owner,)).fetchone()
    clock(db,owner,pet['uid'],now=now)
    if not prior or prior[0]!=pet['uid']:return None
    policy=catalog()['local_policy'];seconds=min(seconds,max(0,now-prior[1]),policy['max_credited_seconds_per_clear'])
    if seconds<=0:return None
    rate=1 if status(pet)==3 else 2 # half-satiety units / second: native stage factors 0.5 / 1.
    fed=min(seconds,max(0,((pet['satiety']-policy['min_growth_satiety'])*2-pet['hunger_remainder'])//rate))
    pet['growth']=min(threshold(pet),pet['growth']+fed*policy['growth_points_per_battle_second'])
    hunger=seconds*rate+pet['hunger_remainder'];pet['satiety']=max(0,pet['satiety']-hunger//2);pet['hunger_remainder']=hunger%2
    save(db,owner,pet)
    return pet

def handle(path,owner,kind,payload,operation):
    owner=character_uid(owner)
    if not isinstance(operation,str) or not 1<=len(operation)<=160:raise ValueError('Pet feeding operation identity')
    digest=hashlib.sha256(struct.pack('>I',kind)+payload).hexdigest()
    from els_server.storage.companion_state import ensure as companions,rows
    from els_server.storage.inventory_state import load_items
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');companions(db);ensure(db)
        prior=db.execute('SELECT digest,context FROM pet_feeding_receipts WHERE owner=? AND operation=?',(owner,operation)).fetchone()
        if prior:
            if prior[0]!=digest:raise ValueError('Conflicting pet feeding retry')
            context=json.loads(prior[1]);pet=next(p for p in rows(db,owner,'pet') if p['uid']==context['pet'])
            if active(db,owner)['uid']!=pet['uid']:raise ValueError('Feed retry no longer targets the active pet')
            answer=[wire.feed(pet,**delta(load_items(db,owner),context['item']))]
            for event in answer:encode_event(event)
            return answer
        if kind==0x2f5:
            if len(payload)!=10:raise ValueError('Pet feed request length')
            item_uid,_,_=struct.unpack('>QBB',payload) # original two talk-box choices, not quantities.
            pet=active(db,owner);item=next((i for i in load_items(db,owner) if i['uid']==item_uid),None)
            if item is None:raise ValueError('Owned feed item required')
            from els_server.domain.item_expiration import require_current
            from els_server.domain.item_locks import require_unlocked
            require_current(item);require_unlocked(item);rules=catalog();t=item['template']
            if t in rules['restricted']:raise ValueError('Restricted pet food')
            amount=rules['feeds'].get(str(t))
            if amount is None:
                from els_server.domain.normal_equipment import definitions
                if item['group']!=1 or t not in definitions():raise ValueError('Ordinary bag equipment or registered pet feed required')
                amount=rules['equipment_satiety']
            if pet['satiety']>=4800:raise ValueError('Pet is full')
            # User-approved local feeding: native satiety values, no invented
            # feeding-to-affinity shortcut; growth comes from completed battle.
            pet['satiety']=min(4800,pet['satiety']+amount)
            if str(t) in rules['nutrients']:pet['nutrition']=min(32767,pet['nutrition']+rules['nutrients'][str(t)]['points'])
            if item['count']>1:
                db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,owner));remaining=dict(item,count=item['count']-1)
            else:
                from els_server.storage.item_instances import remove
                remove(db,owner,item);remaining=None
            save(db,owner,pet)
            # Eating gestures follow the original AI -> 2EF path; do not inject
            # a second animation notification from the feeding transaction.
            answer=[wire.feed(pet,updates=[remaining] if remaining else [],removed=None if remaining else item),wire.progress(owner,pet)]
            context=dict(pet=pet['uid'],item=item)
        else:raise ValueError('Unknown pet progression operation')
        db.execute('INSERT INTO pet_feeding_receipts VALUES (?,?,?,?)',(owner,operation,digest,json.dumps(context,sort_keys=True)))
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        for event in answer:encode_event(event)
        return answer
