"""Pet-scoped pickup, character entitlements, consumption, retries and rollback."""
import sqlite3,struct,sys,tempfile
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.companion_state import handle as companion,snapshot
from els_server.storage.pet_support import handle,automatic,initialization
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event

def rejected(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Bad pet request accepted')

def use(item,pet=0):return struct.pack('>QQiiIB',item,pet,0,0,0,0)
def settings(pet=0,hp=50,mp=50,hp_seconds=0,mp_seconds=0,enabled=1):return struct.pack('>QBBbiiBBB',0,hp,mp,enabled,hp_seconds,mp_seconds,40,0,0)

with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'pets.sqlite3';a=LocalAccount(LocalState(path));a.enable_characters();a.get_inventory_snapshot()
    second=a.characters.create('OtherPet',1,'other');a.for_character(second['uid']).get_inventory_snapshot()
    with closing(sqlite3.connect(path)) as db,db:
        items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n) for t,n in ((550427,2),(500720,2),(164566,2),(330562,2),(77000,5))])
    pickup,expand,upgrade,potion=[next(i for i in items if i['template']==t) for t in (500720,164566,330562,77000)]
    for petitem,name in zip([i for i in items if i['template']==550427],('FirstPet','SecondPet')):companion(path,1001,0x2e8,struct.pack('>Q',petitem['uid'])+wstring(name),name)
    pets=snapshot(path,1001)['companions'];p1,p2=pets
    assert handle(path,second['uid'],0x219,use(pickup['uid'],p1['uid']),'steal') is None
    rejected(lambda:handle(path,1001,0x219,use(pickup['uid'],second['uid']),'foreign-pet'))
    rejected(lambda:handle(path,1001,0x219,use(upgrade['uid']),'upgrade-before-expand'))
    ack=handle(path,1001,0x219,use(pickup['uid'],p1['uid']),'pickup')
    assert [e.kind for e in ack]==[0x21a,0x2fc]
    assert [p.get('pickup',False) for p in snapshot(path,1001)['companions']]==[True,False]
    handle(path,1001,0x219,use(pickup['uid'],p1['uid']),'pickup')
    rejected(lambda:handle(path,1001,0x219,use(pickup['uid'],p1['uid']),'duplicate-pickup'))
    rejected(lambda:handle(path,1001,0x219,use(pickup['uid'],p2['uid']),'pickup'))
    from els_server.protocol import pet_support_messages as wire
    original=wire.settings
    def broken(*a,**kw):raise ValueError('Injected native encoding failure')
    wire.settings=broken
    try:rejected(lambda:handle(path,1001,0x219,use(expand['uid']),'rollback'))
    finally:wire.settings=original
    with closing(sqlite3.connect(path)) as db:
        assert automatic(db,1001)['automatic']==0
        assert next(i for i in load_items(db) if i['uid']==expand['uid'])['count']==2
    assert handle(path,1001,0x219,use(expand['uid']),'expand')[-1].kind==0xb3b
    rejected(lambda:handle(path,1001,0x219,use(expand['uid']),'duplicate-expand'))
    rejected(lambda:handle(path,1001,0x661,settings(p1['uid'],100),'threshold-before-upgrade'))
    handle(path,1001,0x219,use(upgrade['uid']),'upgrade')
    from els_server.domain.quick_bindings import item_binding
    binding=item_binding(77000)
    handle(path,1001,0x661,settings(p1['uid'],100),'settings')
    handle(path,1001,0x8a1,struct.pack('>iIiiii',2,2,0,binding,1,0),'bindings')
    rejected(lambda:handle(path,1001,0x8a1,struct.pack('>iIiiii',2,2,0,2147483647,1,0),'unowned-binding'))
    rejected(lambda:handle(path,1001,0x8a1,struct.pack('>iIiiii',2,2,0,0,1,binding),'hp-potion-in-mp-slot'))
    with closing(sqlite3.connect(path)) as db:
        assert automatic(db,1001)['automatic']==automatic(db,1001)['upgrade']==1
        assert automatic(db,second['uid'])['automatic']==0
        assert next(i for i in load_items(db) if i['uid']==pickup['uid'])['count']==1
        assert next(i for i in load_items(db) if i['uid']==expand['uid'])['count']==1
        assert next(i for i in load_items(db) if i['uid']==upgrade['uid'])['count']==1
    assert len(initialization(path,1001).payload)==24
    from els_server.storage.consumables import use as use_consumable
    def consume(*a,**kw):return use_consumable(*a,automatic_use=True,**kw)
    request=struct.pack('>HBBB',0,0,0,0)
    rejected(lambda:consume(path,1001,request,'no-active',now=1000))
    companion(path,1001,0x2ec,struct.pack('>Q',p1['uid']),'summon')
    result=consume(path,1001,request,'auto-use',now=1000);assert [e.kind for e in result]==[0x65f,0x115]
    assert len(consume(path,1001,request,'auto-use',now=1001))==1
    rejected(lambda:consume(path,1001,request,'cooldown',now=1001))
    with closing(sqlite3.connect(path)) as db:assert next(i for i in load_items(db) if i['uid']==potion['uid'])['count']==4
    session=LocalSession(a,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
    session.role='game';session.phase='town_ready'
    assert session.handle(Event(0x202,kind=0x661,payload=settings(p1['uid'],90)),700)[0].kind==0x662
    assert session.handle(Event(0x202,kind=0x2fb,payload=struct.pack('>Q',p1['uid'])),701)[0].kind==0x2fc
    session.phase='dungeon_active'
    from unittest.mock import patch
    with patch('els_server.storage.consumables.time.time',return_value=1040):
        assert [e.kind for e in session.handle(Event(0x202,kind=0x65e,payload=request),703)]==[0x65f,0x115]
    assert struct.unpack_from('>i',session.handle(Event(0x202,kind=0x219,payload=use(pickup['uid'],p2['uid'])),702)[0].payload)[0]!=0
    session.phase='town_ready'
    with closing(sqlite3.connect(path)) as db,db:
        gems=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=21,quantity=1) for t in (135974,135975,135976)])
    def equip(gem,slot=1):return struct.pack('>QiQ',p1['uid'],slot,gem['uid'])
    rejected(lambda:handle(path,second['uid'],0x8c7,equip(gems[0]),'steal-gem'))
    rejected(lambda:handle(path,1001,0x8c7,equip(gems[0],3),'bad-slot'))
    rejected(lambda:handle(path,1001,0x8c7,equip(gems[0]),'bad-rng',randbelow=lambda n:n))
    result=handle(path,1001,0x8c7,equip(gems[0]),'equip',randbelow=lambda n:0)
    assert result[0].kind==0x8c8
    first=snapshot(path,1001)['companions'][0];assert first['equipment'][1]==dict(template=135974,socket=110200)
    handle(path,1001,0x8c7,equip(gems[0]),'equip',randbelow=lambda n:1/0)
    assert snapshot(path,1001)['companions'][0]==first
    original=wire.equipment_ack;wire.equipment_ack=broken
    try:rejected(lambda:handle(path,1001,0x8c7,equip(gems[1]),'equip-rollback',randbelow=lambda n:0))
    finally:wire.equipment_ack=original
    assert snapshot(path,1001)['companions'][0]==first
    handle(path,1001,0x8c7,equip(gems[1]),'replace',randbelow=lambda n:0)
    secondgear=snapshot(path,1001)['companions'][0]['equipment'];assert secondgear[1]['template']==135975
    # Slot 2 rolls the verified potion cooldown family, one stable option.
    rolls=iter((4,0));handle(path,1001,0x8c7,equip(gems[2],2),'second-slot',randbelow=lambda n:next(rolls))
    rejected(lambda:handle(path,1001,0x8c7,struct.pack('>QiQ',p1['uid'],1,0),'unplug'))
    from els_server.storage.pet_support import active_effects
    with closing(sqlite3.connect(path)) as db:
        effects=active_effects(db,1001);assert effects['m_fPetAdditionalPowerRate']==.03 and effects['m_fReduceRecoveryItemCooltime']==.055
        assert not any(i['uid'] in {g['uid'] for g in gems} for i in load_items(db))
    handle(path,1001,0x661,settings(hp_seconds=60),'timer-mode')
    consume(path,1001,request,'timer-use',now=1100)
    rejected(lambda:consume(path,1001,request,'too-early-timer',now=1135))
    consume(path,1001,request,'timer-ready',now=1160)
    handle(path,1001,0x661,settings(enabled=0),'disable-automatic')
    rejected(lambda:consume(path,1001,request,'automatic-off',now=1220))
print('PASS: pickup ownership, character entitlements, atomic consumption/rollback, duplicate handling, automatic settings and consumable cooldown.')
