"""The catalog integration fixture is isolated, Town-only and never grants goods."""
import sqlite3,struct,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event
from shop_messages import availability_notice,empty_catalog_ack,empty_cart_ack,empty_deposit_ack

args=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
with tempfile.TemporaryDirectory() as d:
    account=LocalAccount(LocalState(Path(d)/'isolated.sqlite3'))
    session=LocalSession(account,shop_test=True,**args)
    before=account.get_inventory_snapshot()
    request=Event(0x202,kind=0xd78,payload=struct.pack('>i',1))
    assert session.handle(request)==[empty_catalog_ack(False)]
    session.role='game';session.phase='map_loading'
    session.handle(Event(0x202,kind=0x225,payload=struct.pack('>i',20000)+b'\0'))
    ready=Event(0x202,kind=0x227,payload=struct.pack('>fffBH',0,0,0,0,0))
    session.handle(ready)
    assert session.periodic_notifications()==[availability_notice()]
    assert session.periodic_notifications()==[]
    session.handle(ready)
    assert session.periodic_notifications()==[]
    assert session.handle(request)==[empty_catalog_ack()]
    assert session.handle(request)==[empty_catalog_ack()]
    cart=Event(0x202,kind=0x1f1,payload=b'')
    assert session.handle(cart)==[empty_cart_ack()]
    assert session.handle(cart)==[empty_cart_ack()]
    assert empty_cart_ack().payload==bytes(4)
    deposit=Event(0x202,kind=0xd7a,payload=bytes.fromhex('0000001500000001'))
    assert session.handle(deposit)==[empty_deposit_ack()]
    assert empty_deposit_ack().kind==0xd7b and empty_deposit_ack().payload==bytes(20)
    assert session.handle(Event(0x202,kind=0xd7a,payload=bytes(8)))==[empty_deposit_ack(-1)]
    assert session.handle(Event(0x202,kind=0x1f1,payload=b'\0'))==[]
    for bad in [b'',bytes(4),struct.pack('>i',-1),struct.pack('>i',2),struct.pack('>i',1)+b'\0']:
        assert session.handle(Event(0x202,kind=0xd78,payload=bad))==[empty_catalog_ack(False)]
    session.phase='dungeon_active'
    assert session.handle(request)==[empty_catalog_ack(False)]
    assert session.handle(cart)==[]
    assert account.get_inventory_snapshot()==before
    ordinary=LocalSession(account,**args);ordinary.role='game';ordinary.phase='town_ready'
    assert ordinary.handle(request)==[] and ordinary.periodic_notifications()==[]
    assert ordinary.handle(cart)==[]
    try:LocalSession(account,shop_test=True)
    except ValueError:pass
    else:raise AssertionError('Shop accepted outside isolated profile')
print('PASS: shop availability once after Town, full 37-byte empty catalog, invalid selectors/phases rejected, no inventory or economy changes.')
