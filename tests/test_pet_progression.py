"""Feeding conservation, persistent stage boundaries and transactional clear growth."""
import json,sqlite3,struct,sys,tempfile,uuid
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.companion_state import handle as companion,snapshot
from els_server.storage.pet_progression import handle,save,active,clear,clock
from els_server.storage.pet_support import handle as support
from els_server.domain.pet_progression import threshold
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event
from types import SimpleNamespace

def rejected(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Invalid pet operation accepted')

with tempfile.TemporaryDirectory() as d:
    old=Path(d)/'old.sqlite3';sqlite3.connect(old).close()
    from els_server.domain.pet_progression_flow import observe
    legacy=SimpleNamespace(client_build='dx11_260923',item_test=True,reward_receipt={'run_id':'legacy'},account=SimpleNamespace(store=SimpleNamespace(path=old),uid=1001))
    assert observe(legacy,[Event(0x201,kind=0xc1,payload=b'clear')])==[]
    with closing(sqlite3.connect(old)) as db:assert list(db.execute("SELECT name FROM sqlite_master WHERE type='table'"))==[]
    path=Path(d)/'pets.sqlite3';a=LocalAccount(LocalState(path));a.enable_characters();a.get_inventory_snapshot()
    with closing(sqlite3.connect(path)) as db,db:
        items=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n) for t,n in ((500010,1),(550427,1),(500040,5),(500030,2),(30154,1))])
    for t,name in ((500010,'Egg'),(550427,'Moca')):
        item=next(i for i in items if i['template']==t);companion(path,1001,0x2e8,struct.pack('>Q',item['uid'])+wstring(name),name)
    pets=snapshot(path,1001)['companions'];egg=next(p for p in pets if p['name']=='Egg');moca=next(p for p in pets if p['name']=='Moca')
    fruit=next(i for i in items if i['template']==500040);gear=next(i for i in items if i['template']==30154)
    feed=lambda uid:struct.pack('>QBB',uid,255,255)
    rejected(lambda:handle(path,1001,0x2f5,feed(fruit['uid']),'no-pet'))
    with patch('els_server.storage.pet_progression.time.time',return_value=1000):companion(path,1001,0x2ec,struct.pack('>Q',egg['uid']),'summon')
    reply=handle(path,1001,0x2f5,feed(fruit['uid']),'feed')
    assert [r.kind for r in reply]==[0x2f6,0x2f4]
    p=snapshot(path,1001)['companions'][0];assert p['satiety']==4776 and p['nutrition']==3 and p['growth']==0
    assert len(handle(path,1001,0x2f5,feed(fruit['uid']),'feed'))==1
    handle(path,1001,0x2f5,feed(fruit['uid']),'cap');assert snapshot(path,1001)['companions'][0]['satiety']==4800
    rejected(lambda:handle(path,1001,0x2f5,feed(fruit['uid']),'full'))
    rejected(lambda:handle(path,1001,0x2f5,feed(gear['uid']),'feed'))
    with closing(sqlite3.connect(path)) as db,db:
        p=active(db,1001);p['satiety']=3000;save(db,1001,p)
    handle(path,1001,0x2f5,feed(gear['uid']),'equipment')
    with closing(sqlite3.connect(path)) as db:
        assert not any(i['uid']==gear['uid'] for i in load_items(db,1001))
        assert next(i for i in load_items(db,1001) if i['uid']==fruit['uid'])['count']==3
    # Response encoding failure must roll back both food and pet changes.
    before=snapshot(path,1001)
    with patch('els_server.protocol.pet_progression_messages.feed',side_effect=ValueError('Injected encoding failure')):
        rejected(lambda:handle(path,1001,0x2f5,feed(fruit['uid']),'rollback'))
    assert snapshot(path,1001)==before
    with closing(sqlite3.connect(path)) as db,db:
        p=active(db,1001);p['satiety']=3840;p['growth']=threshold(p)-10;save(db,1001,p);clock(db,1001,p['uid'],now=1000)
    # Only a committed server clear receipt grants growth; failed encoding and
    # replay cannot advance it. The close-to-threshold state is a unit fixture.
    run=str(uuid.uuid4());before=snapshot(path,1001)
    with patch('els_server.storage.pet_progression.time.time',return_value=1002):
        rejected(lambda:a.reward_store.grant(run,b'clear-proof',0,0,lambda *_:(_ for _ in ()).throw(ValueError('Fail')),dungeon_clear=(30000,2)))
        assert snapshot(path,1001)==before
        result=a.reward_store.grant(run,b'clear-proof',0,0,lambda *_:b'clear',dungeon_clear=(30000,2))
        assert not result['replayed']
        full=snapshot(path,1001);assert full['companions'][0]['growth']==38160
        assert a.reward_store.grant(run,b'clear-proof',0,0,lambda *_:b'clear',dungeon_clear=(30000,2))['replayed']
        assert snapshot(path,1001)==full
    evolution=support(path,1001,0x2fb,struct.pack('>Q',egg['uid']),'evolve')
    assert [e.kind for e in evolution]==[0x2fc,0x2fd]
    p=snapshot(path,1001)['companions'][0];assert (p['step'],p['growth'])==(1,0)
    assert len(support(path,1001,0x2fb,struct.pack('>Q',egg['uid']),'evolve'))==1
    rejected(lambda:support(path,1001,0x2fb,struct.pack('>Q',egg['uid']),'not-ready'))
    rejected(lambda:support(path,1001,0x2fb,struct.pack('>Q',moca['uid']),'already-adult'))
    for stage in (2,3):
        with closing(sqlite3.connect(path)) as db,db:
            p=active(db,1001);p['growth']=threshold(p);save(db,1001,p)
        support(path,1001,0x2fb,struct.pack('>Q',egg['uid']),'stage'+str(stage))
        assert snapshot(path,1001)['companions'][0]['step']==stage
    rejected(lambda:support(path,1001,0x2fb,struct.pack('>Q',egg['uid']),'past-adult'))
    # Hunger gates growth and adult satiety uses the native half-rate factor.
    with closing(sqlite3.connect(path)) as db,db:
        p=active(db,1001);p.update(satiety=1919,growth=0,hunger_remainder=0);save(db,1001,p);clock(db,1001,p['uid'],now=2000)
        p=clear(db,1001,61,now=2061);assert (p['growth'],p['satiety'],p['hunger_remainder'])==(0,1889,1)
    with patch('els_server.storage.pet_progression.time.time',return_value=3000):snapshot(path,1001,enter_world=True)
    with closing(sqlite3.connect(path)) as db,db:
        p=clear(db,1001,3600,now=3000);assert p is None # offline time is never banked.
    companion(path,1001,0x2ec,struct.pack('>Q',moca['uid']),'switch')
    rejected(lambda:handle(path,1001,0x2f5,feed(fruit['uid']),'feed'))
    other=a.characters.create('OtherPet',1,'other');a.for_character(other['uid']).get_inventory_snapshot()
    rejected(lambda:handle(path,other['uid'],0x2f5,feed(fruit['uid']),'foreign'))
    rejected(lambda:support(path,other['uid'],0x2fb,struct.pack('>Q',egg['uid']),'foreign-evolve'))
    session=LocalSession(a,enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
    session.role='game';session.phase='dungeon_loading'
    assert struct.unpack_from('>i',session.handle(Event(0x202,kind=0x2f5,payload=feed(fruit['uid'])),10)[0].payload)[0]==-1
    session.phase='town_ready';assert session.handle(Event(0x202,kind=0x2f5,payload=feed(fruit['uid'])),11)[0].kind==0x2f6
print('PASS: feed ownership/conservation/retry/rollback, clear-receipted growth, hunger/offline limits, all evolution boundaries and persisted native state.')
