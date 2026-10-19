"""Activation conservation, retry/rollback, ownership and persisted summon state."""
import sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.storage.companion_state import handle,snapshot
from els_server.domain.companions import catalog
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event

def fail(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Rejected request accepted')

with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'companions.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters();account.get_inventory_snapshot()
    second=account.characters.create('PetOwner2',1,'create-owner');account.for_character(second['uid']).get_inventory_snapshot()
    with closing(sqlite3.connect(path)) as db,db:
        items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=4,quantity=1) for t in (550427,550431,90002290)])
    pet,mount,randompet=items
    request=struct.pack('>Q',pet['uid'])+wstring('ShopMoca')
    fail(lambda:handle(path,second['uid'],0x2e8,request,'steal'))
    fail(lambda:handle(path,1001,0x2e8,request[:-1],'truncated'))
    fail(lambda:handle(path,1001,0x2e8,struct.pack('>Q',pet['uid'])+wstring('NameTooLong123'),'bad-name'))
    fail(lambda:handle(path,1001,0x2e8,request,'bad-rng',randbelow=lambda n:n))
    ack=handle(path,1001,0x2e8,request,'activate')
    assert ack.kind==0x2e9 and struct.unpack_from('>i',ack.payload)[0]==0
    assert handle(path,1001,0x2e8,request,'activate',randbelow=lambda n:1/0)==ack
    fail(lambda:handle(path,1001,0x2e8,request,'other-retry'))
    fail(lambda:handle(path,1001,0x432,struct.pack('>Q',mount['uid']),'activate'))
    handle(path,1001,0x432,struct.pack('>Q',mount['uid']),'mount')
    handle(path,1001,0x2e8,struct.pack('>Q',randompet['uid'])+wstring('Random'),'random',randbelow=lambda n:n-1)
    saved=snapshot(path,1001);assert len(saved['companions'])==3
    p=next(p for p in saved['companions'] if p['name']=='ShopMoca');m=next(p for p in saved['companions'] if p['kind']=='mount')
    assert (p['unit'],m['unit'])==(226,105)
    assert next(p for p in saved['companions'] if p['name']=='Random')['unit']==30016
    fail(lambda:handle(path,second['uid'],0x2ec,struct.pack('>Q',p['uid']),'steal-summon'))
    handle(path,1001,0x2ec,struct.pack('>Q',p['uid']),'summon')
    handle(path,1001,0x42c,struct.pack('>QB',m['uid'],1),'mount-summon')
    saved=snapshot(path,1001);assert (saved['pet'],saved['mount'],saved['mounted'])==(p['uid'],m['uid'],True)
    handle(path,1001,0x42f,struct.pack('>Qi',m['uid'],0),'dismount')
    handle(path,1001,0x2ec,bytes(8),'unsummon')
    assert snapshot(path,1001)['pet']==0 and not snapshot(path,1001)['mounted']
    assert snapshot(path,second['uid'])['companions']==[]
    with closing(sqlite3.connect(path)) as db:
        assert all(i['uid'] not in {pet['uid'],mount['uid'],randompet['uid']} for i in load_items(db))
        assert db.execute('SELECT COUNT(*) FROM companion_receipts').fetchone()[0]==7
    session=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
    session.role='game';session.phase='town_ready'
    reply=session.handle(Event(0x202,kind=0x2ea,payload=struct.pack('>iiB',1,0,0)),400)
    assert reply[0].kind==0x2eb and struct.unpack_from('>i',reply[0].payload)[0]==0
    session.phase='channels_ready'
    assert struct.unpack_from('>i',session.handle(Event(0x202,kind=0x2ec,payload=struct.pack('>Q',p['uid'])),401)[0].payload)[0]!=0
    from els_server.protocol import companion_messages as wire
    with closing(sqlite3.connect(path)) as db,db:
        extra=grant_items(db,[dict(template=550427,metadata=VERIFIED_TEMPLATES[550427],group=4,quantity=1)])[0]
    before=snapshot(path,1001);original_encoder=wire.activation_ack
    def broken_encoder(*args,**kwargs):raise ValueError('Injected encoding failure')
    try:
        wire.activation_ack=broken_encoder
        fail(lambda:handle(path,1001,0x2e8,struct.pack('>Q',extra['uid'])+wstring('Rollback'),'encode-failure'))
    finally:wire.activation_ack=original_encoder
    assert snapshot(path,1001)==before
    with closing(sqlite3.connect(path)) as db,db:
        assert any(i['uid']==extra['uid'] and i['count']==1 for i in load_items(db))
        for n in range(7):db.execute('INSERT INTO companions VALUES (?,?,?,?,?,?)',(1005000+n,1001,'pet',226,'Page'+str(n),999))
    session.phase='town_ready'
    page=session.handle(Event(0x202,kind=0x2ea,payload=struct.pack('>iiB',2,0,0)),402)[0]
    assert struct.unpack_from('>iIII',page.payload)==(0,2,2,3)
    whole=session.handle(Event(0x202,kind=0x2ea,payload=struct.pack('>iiB',0,0,0)),403)[0]
    assert struct.unpack_from('>iIII',whole.payload)==(0,2,1,9)
    mount_list=session.handle(Event(0x202,kind=0x42a,payload=b'\0'),404)[0]
    assert mount_list.kind==0x42b and struct.unpack_from('>iI',mount_list.payload)==(0,1)
    handle(path,1001,0x2ec,struct.pack('>Q',p['uid']),'restore-active')
    handle(path,1001,0x42c,struct.pack('>QB',m['uid'],1),'restore-mount')
    restored=snapshot(path,1001,enter_world=True)
    assert restored['pet']==p['uid'] and restored['mount']==0 and not restored['mounted']
    assert wire.initialization(restored).kind==0x2d
from els_server.domain.shop_additions import catalog as shop_catalog
for category,kind in ((61,'pet'),(63,'mount')):
    for row in shop_catalog('standalone')['offers']:
        if row['category']==category:assert row['template'] in catalog()[kind] and catalog()[kind][row['template']]['duration']==-1
print('PASS: native mappings cover shop pets/mounts; activation conserves items, retries/rollback, ownership, random weights and persisted summon state.')
