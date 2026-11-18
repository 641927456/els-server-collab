"""Native 8AD/8AF/8B9 pet nutrient, growth-point and digestive requests.

Covers the reported symptom: the pet-information window's "digestion time" and
"growth points" stayed at zero because none of the three native requests had a
handler at all. This exercises the owned transaction on a real save.
"""
import sqlite3,struct,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.companion_state import handle as companion,snapshot,rows
from els_server.storage.pet_progression import ensure as ensure_progression,save as save_pet
from els_server.domain.pet_progression import template,threshold,status
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.storage.pet_nutrition import perform,request

OWNER=1001

def nutrient_request(pet,rows_):return struct.pack('>I',len(rows_))+b''.join(struct.pack('>Qi',uid,n)for uid,n in rows_)+struct.pack('>QB',pet,1)
def invest_request(pet,rows_):return struct.pack('>QI',pet,len(rows_))+b''.join(struct.pack('>ih',k,v)for k,v in rows_)
def digest_request(pet,item):return struct.pack('>Qi',pet,item)
def result(event):return struct.unpack_from('>i',event.payload)[0]

with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'nutrition.sqlite3';a=LocalAccount(LocalState(path));a.enable_characters();a.get_inventory_snapshot()
    with closing(sqlite3.connect(path)) as db,db:
        items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)
            for t,n in ((550427,1),(135979,3),(135977,3))])
    pet_item=next(i for i in items if i['template']==550427)
    big=next(i for i in items if i['template']==135979)   # 3 points / 3 hours
    small=next(i for i in items if i['template']==135977) # 1 point / 3 hours
    companion(path,OWNER,0x2e8,struct.pack('>Q',pet_item['uid'])+wstring('TestPet'),'TestPet')
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');ensure_progression(db)
        pet=next(p for p in rows(db,OWNER,'pet'))
        pet.update(step=template(pet['unit'])['EVOLUTION_ALL_STEP'],growth=threshold(dict(pet,step=0)),
            satiety=2400,nutrition=0,digest_until=0,personality={})
        pet['growth']=threshold(pet);save_pet(db,OWNER,pet)
    pet=next(p for p in snapshot(path,OWNER)['companions'])
    account_id=a.account_id;guard=lambda db:None
    def call(kind,payload,operation,now=None):
        return perform(path,OWNER,account_id,kind,payload,operation,guard,now=now)

    # 8AD: two stacks of the 3-point nutrient -> +6 points, +6 hours.
    answer=call(0x8ad,nutrient_request(pet['uid'],[(big['uid'],2)]),'nut-1',now=1_000_000)
    assert [e.kind for e in answer]==[0x8ae],answer
    assert result(answer[0])==0
    with closing(sqlite3.connect(path)) as db:live=next(p for p in rows(db,OWNER,'pet'))
    assert (live["nutrition"],live["digest_until"])==(6,1_000_000+6*3600),(live['nutrition'],live['digest_until'])
    # 2DCD260 reads result, growth points, the 64-bit digestion deadline, the
    # changed inventory records, then the pet UID. The deadline must be a full
    # eight-byte field: a 32-bit slot shifts the record block by four bytes, the
    # client reads a nonsense record count and drops the reply outright.
    ack=answer[0].payload
    assert struct.unpack_from('>ih',ack)==(0,6),ack.hex()
    assert struct.unpack_from('>Q',ack,6)[0]==1_000_000+6*3600,ack.hex()
    assert struct.unpack_from('>I',ack,14)[0]==1,'one changed record'+ack.hex()
    assert struct.unpack_from('>Q',ack,len(ack)-8)[0]==pet['uid'],ack.hex()
    # D9C550 DTO+3D is the digestion deadline, not the pet's own expiry:
    # 30173B0/35F1C60 subtract the native current time from that slot to render
    # PetGrowthDigestTimeValue. It must sit immediately before nutrition, and it
    # must reach the panel through the ordinary 2EB list.
    from els_server.protocol.companion_messages import pet_record,pet_list
    record=pet_record(live)
    at=record.find(struct.pack('>Q',live['digest_until']))
    assert at>0 and struct.unpack_from('>h',record,at+8)[0]==live['nutrition'],(at,record.hex())
    listed=pet_list(0,[live]).payload
    assert struct.pack('>Q',live['digest_until'])+struct.pack('>h',live['nutrition']) in listed
    with closing(sqlite3.connect(path)) as db:
        assert next(i for i in load_items(db,OWNER) if i['uid']==big['uid'])['count']==1
    # Replaying the same operation must not consume again.
    again=call(0x8ad,nutrient_request(pet['uid'],[(big['uid'],2)]),'nut-1',now=1_000_000)
    assert [e.kind for e in again]==[0x8ae]
    with closing(sqlite3.connect(path)) as db:
        assert next(i for i in load_items(db,OWNER)if i['uid']==big['uid'])['count']==1
        assert next(p for p in rows(db,OWNER,'pet'))['nutrition']==6
    # A drag asking for more than the stack holds is clamped to the owned
    # count instead of refusing: the panel caches the size it opened with.
    with closing(sqlite3.connect(path)) as db:owned_before=len(load_items(db,OWNER))
    answer=call(0x8ad,nutrient_request(pet['uid'],[(big['uid'],99)]),'nut-clamp',now=1_000_000)
    assert result(answer[0])==0
    with closing(sqlite3.connect(path)) as db:
        live=next(p for p in rows(db,OWNER,'pet'))
        assert live['nutrition']==9,(live['nutrition'],)  # 6 + 3 from the last stack
        assert len(load_items(db,OWNER))==owned_before-1  # the emptied stack is removed

    # 8AF: allocate the available points across two abilities, capped per ability.
    answer=call(0x8af,invest_request(pet['uid'],[(0,3),(2,3)]),'inv-1',now=1_000_000)
    assert [e.kind for e in answer]==[0x8b0] and result(answer[0])==0,answer
    with closing(sqlite3.connect(path)) as db:live=next(p for p in rows(db,OWNER,'pet'))
    assert live['nutrition']==3 and live['personality']=={'0':3,'2':3},(live['nutrition'],live['personality'])
    try:
        call(0x8af,invest_request(pet['uid'],[(1,5)]),'inv-broke',now=1_000_000);raise AssertionError('no balance must fail')
    except ValueError as e:assert 'Insufficient pet growth points'in str(e),e
    with closing(sqlite3.connect(path)) as db:
        assert next(p for p in rows(db,OWNER,'pet'))['personality']=={'0':3,'2':3}

    # 8B9: one digestive item removes two hours from the deadline. The native
    # digestive templates are outside the verified bag catalog, so the mapping
    # is stubbed onto a verified stack to exercise the transaction itself.
    with patch('els_server.storage.pet_nutrition.decreases',return_value={135977:7200}):
        answer=call(0x8b9,digest_request(pet['uid'],135977),'dig-1',now=1_000_000+60)
        assert [e.kind for e in answer]==[0x105,0x8ba] and result(answer[-1])==0,answer
        with closing(sqlite3.connect(path)) as db:live=next(p for p in rows(db,OWNER,'pet'))
        assert live['digest_until']==1_000_000+9*3600-2*3600,live['digest_until']
        with closing(sqlite3.connect(path)) as db:
            assert next(i for i in load_items(db,OWNER)if i['uid']==small['uid'])['count']==2
        try:
            call(0x8b9,digest_request(pet['uid'],135981),'dig-unknown',now=1_000_000);raise AssertionError('unregistered digestive must fail')
        except ValueError as e:assert 'digestive template'in str(e),e

    # The dispatch chain now answers 0x8AD end to end instead of dropping it.
    session=LocalSession(a,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,
        gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
    session.role='game';session.phase='town_ready'
    routed=session.handle(Event(0x202,kind=0x8ad,payload=nutrient_request(pet['uid'],[(small['uid'],1)])),900)
    assert routed and routed[0].kind==0x8ae,'0x8AD must be answered'
    assert result(routed[0])==0,'a committed nutrient request must succeed'
    with closing(sqlite3.connect(path)) as db:
        live=next(p for p in rows(db,OWNER,'pet'))
        assert live['nutrition']==4 and live['digest_until']>0,(live['nutrition'],live['digest_until'])
        assert next(i for i in load_items(db,OWNER) if i['uid']==small['uid'])['count']==1
print('PASS: native 8AD/8AF/8B9 add growth points, extend digestion time, allocate and shorten it; replay is idempotent.')
