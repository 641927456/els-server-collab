"""Original8AD nutritional refill and8B9 digestive refill in the item transaction."""
from contextlib import closing
import sqlite3,struct,time
from els_server.domain.pet_digestion import decreases,nutrient,MAX_DIGEST_SECONDS
from els_server.domain.pet_progression import template,status
from els_server.protocol import pet_progression_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_management import _updates
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove
from els_server.storage.pet_support import owned_pet
from els_server.storage.pet_progression import ensure,save
from els_server.storage.npc_trade import balances

def request(kind,payload):
    if kind==0x8b9:
        if len(payload)!=12:raise ValueError('Pet digestive request length')
        pet,item=struct.unpack('>Qi',payload)
        if item not in decreases():raise ValueError('Original pet digestive template')
        return pet,item
    if kind!=0x8ad or len(payload)<25:raise ValueError('Pet nutrient request length')
    n,=struct.unpack_from('>I',payload)
    if not 1<=n<=36 or len(payload)!=4+n*12+9:raise ValueError('Pet nutrient request count/length')
    rows=[struct.unpack_from('>Qi',payload,4+i*12)for i in range(n)]
    pet,flag=struct.unpack_from('>QB',payload,4+n*12)
    if flag!=1 or len({uid for uid,count in rows})!=n or any(not 0<uid<2**63 or count<=0 for uid,count in rows):raise ValueError('Pet nutrient original list')
    return pet,rows

def authority(db,owner,account,guard,pet_uid):
    guard(db)
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    require_active_character(db,owner);require_owner(db,owner,account)
    pet=owned_pet(db,owner,pet_uid)
    if pet['step']!=template(pet['unit'])['EVOLUTION_ALL_STEP']or status(pet)!=3:raise ValueError('Fully grown pet required')
    return pet

def answer(kind,pet,changes):
    if kind==0x8b9:return _updates(changes)+[wire.digestion(pet)]
    # Nutrient ACK carries all changed inventory records, including removals.
    from els_server.protocol.companion_messages import event
    from els_server.domain.fashion_state import move_ack
    data=struct.pack('>ihQ',0,pet['nutrition'],pet['digest_until'])
    data+=move_ack(changes)[:-4]
    return[event(0x8ae,data+struct.pack('>Q',pet['uid']))]

def perform(path,owner,account,kind,payload,operation,guard,*,now=None):
    pet_uid,value=request(kind,payload)
    owner,digest=_identity(owner,kind,payload,operation)
    stamp=int(time.time())if now is None else now
    if type(stamp)is not int or not 0<stamp<2**40-MAX_DIGEST_SECONDS:raise ValueError('Pet digestive clock')
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');ensure(db)
        pet=authority(db,owner,account,guard,pet_uid)
        before=load_items(db,owner);old=_previous(db,operation,digest);balance=balances(db,owner)
        if old is not None:
            events=answer(kind,pet,current_changes(db,operation,owner,kind,old,before))
            for event in events:encode_event(event)
            authority(db,owner,account,guard,pet_uid);return events
        if balance['revision']>=2**63-1:raise ValueError('Pet nutrient revision bound')
        if kind==0x8b9:
            if pet['digest_until']<=stamp:raise ValueError('Pet has no digestion time to reduce')
            item=next((i for i in before if i['template']==value),None)
            if item is None:raise ValueError('Owned digestive item required')
            selected=[(item,1)];pet['digest_until']=max(stamp,pet['digest_until']-decreases()[value])
        else:
            owned={i['uid']:i for i in before};selected=[];points=0;seconds=0
            for uid,count in value:
                item=owned.get(uid)
                if item is None or count>item['count']:raise ValueError('Owned nutrient quantity required')
                p,hours=nutrient(item);points+=p*count;seconds+=hours*count;selected.append((item,count))
            until=max(stamp,pet['digest_until'])+seconds
            if until>stamp+MAX_DIGEST_SECONDS or pet['nutrition']+points>32767:raise ValueError('Pet nutrient capacity')
            pet.update(nutrition=pet['nutrition']+points,digest_until=until)
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        positions=[]
        for item,count in selected:
            require_current(item,now=stamp);require_unlocked(item,now=stamp)
            if item.get('sealed',False):raise ValueError('Sealed pet nutrient item')
            positions.append((item['group'],item['slot']))
            if count==item['count']:remove(db,owner,item)
            else:db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=?',(count,item['uid'],owner))
        save(db,owner,pet);after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        events=answer(kind,pet,[(p,current.get(p))for p in positions])
        for event in events:encode_event(event)
        if authority(db,owner,account,guard,pet_uid)!=pet or balances(db,owner)!=balance:raise ValueError('Pet nutrient late authority changed')
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,kind,positions,before,after)
        return events
