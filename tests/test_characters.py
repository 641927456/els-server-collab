"""Migration, create/retry and ownership isolation across all 15 character types."""
from contextlib import closing
import sys,sqlite3,tempfile,uuid,struct,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.local_session import LocalAccount,LocalSession,SessionOrderError
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters,BASE_CLASSES
from els_server.storage.reward_state import RewardState
from els_server.storage.inventory_state import InventoryState
from els_server.protocol.character_messages import create_request,create_ack,name_request
from els_server.protocol.local_messages import wstring,i32

with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'save.sqlite3'
    # Exercise a real legacy CHECK constraint, including rollback on failure.
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('CREATE TABLE location (uid INTEGER PRIMARY KEY CHECK(uid=1001),town INTEGER NOT NULL,board INTEGER NOT NULL,progress INTEGER NOT NULL,x REAL NOT NULL,y REAL NOT NULL,z REAL NOT NULL,revision INTEGER NOT NULL)')
        db.execute('INSERT INTO location VALUES (1001,20001,0,0,1,2,3,4)')
    account=LocalAccount(LocalState(path));account.enable_characters()
    assert account.get_location()['map']==20001 and account.get_location()['revision']==4
    roster=account.characters
    for t in range(1,16):
        name=f'角色{t}';op=str(uuid.uuid4());c=roster.create(name,t,op)
        assert c['unit_class']==BASE_CLASSES[t] and c['uid']==1001+t
        assert roster.create(name,t,op)==c
        try:roster.create(name,t,str(uuid.uuid4()))
        except ValueError:pass
        else:raise AssertionError('Duplicate name accepted')
        char=account.for_character(c['uid']);assert char.get_reward_balances()['ed']==0
        starter=char.get_inventory_snapshot()['items']
        assert len(starter)==(15 if t==10 else 10) and sum(i['group']==9 for i in starter)==10
        char.save_location(20000+t%15,0,0,(t,0.,0.))
        receipt=char.enable_rewards().grant(str(uuid.uuid4()),b'isolated-character',t*10,0,item_plan=[dict(template=77000,metadata=2,group=6,quantity=t)],inventory_response_builder=lambda b,i:b'OK')
        assert receipt['items'][0]['count']==t
        wire=wstring(name)+struct.pack('>iiBBI',BASE_CLASSES[t],1,0,0,0)
        assert create_request(wire)['unit_type']==t
        assert name_request(i32(1)+wstring(name))==name
        assert create_ack(c).kind==0x25
        from els_server.domain.character_rules import initial_skills
        assert set(char.get_skills())-{0}==set(initial_skills(c))
        char.equip_skill(struct.pack('>ii',3,initial_skills(c)[0]))
        assert LocalState(path,c['uid']).load_skills()==char.get_skills()
    assert account.get_inventory_snapshot()['items']==[] and account.get_reward_balances()['ed']==0
    ids=[]
    for c in roster.list()[1:]:
        state=InventoryState(path,c['uid']).snapshot();assert state['balances']['ed']==c['unit_type']*10
        potion=next(i for i in state['items'] if i['template']==77000)
        assert potion['count']==c['unit_type'];ids.append(potion['uid'])
    assert len(set(ids))==15
    try:roster.create('超过容量',1,str(uuid.uuid4()))
    except ValueError:pass
    else:raise AssertionError('Capacity not enforced')
    assert len(Characters(path).list())==16
    with closing(sqlite3.connect(path)) as db,db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

with tempfile.TemporaryDirectory() as tmp:
    account=LocalAccount(LocalState(Path(tmp)/'save.sqlite3'));account.enable_characters()
    session=LocalSession(account,enter_town=True,client_build='dx11_260923')
    session.role='game';session.phase='characters_ready'
    # Actual return-to-roster path fetches channels before name validation.
    session.handle(Event(0x202,kind=0x490,payload=b''))
    assert session.phase=='channels_ready'
    for sequence,t in enumerate((2,15),1):
        name=f'创建验证{t}'
        check=session.handle(Event(0x202,kind=0x48b,payload=i32(1)+wstring(name)))
        assert check[0].kind==0x48c and check[0].payload[:4]==bytes(4)
        request=Event(0x202,kind=0x489,payload=wstring(name)+struct.pack('>iiBBI',BASE_CLASSES[t],1,0,0,0))
        first=session.handle(request,request_sequence=sequence)[0]
        assert first.kind==0x25 and first.payload[:4]==bytes(4)
        assert session.handle(request,request_sequence=sequence)[0].payload==first.payload
        assert session.handle(Event(0x202,kind=0x48b,payload=i32(1)+wstring(name)))[0].payload[:4]!=bytes(4)
    assert len(account.characters.list())==3
    session.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',1003)))
    assert session.account.character()['unit_type']==15
    assert session.phase=='player_initialized'
    assert session.account.get_reward_balances()['ed']==0
    session.phase='town_ready'
    session.completed.update((0x6e9,0x5bf,0x32,0x225,0x227))
    session.handle(Event(0x202,kind=0x490,payload=b''))
    session.handle(Event(0x202,kind=0x485,payload=b''))
    assert session.phase=='characters_ready'
    session.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',1002)))
    assert session.phase=='player_initialized' and session.account.uid==1002
    assert not session.completed.intersection((0x6e9,0x5bf,0x32,0x225,0x227))
    session.phase='characters_ready'
    try:session.handle(Event(0x202,kind=0x28,payload=struct.pack('>Q',9999)))
    except SessionOrderError:pass
    else:raise AssertionError('Selected unknown character')
print('PASS: legacy migration preserves state, 15 types create/retry/reload, unique item UIDs, isolated money/inventory/location, duplicate names and capacity.')
