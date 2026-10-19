"""ED purchases must conserve money/items across retries and rollback failures."""
import sqlite3,struct,sys,tempfile
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_session import LocalSession,LocalAccount
from local_state import LocalState
from protocol_codec import Event
from shop_state import catalog,purchase
from shop_messages import ed_catalog_ack,ed_purchase_request
from inventory_state import load_items
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS

args=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True,shop_test=True)
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'shop.sqlite3';account=LocalAccount(LocalState(path))
    session=LocalSession(account,**args);session.role='game';session.phase='town_ready'
    all_offers=catalog(1);assert len(all_offers)>100 and len({p['sku'] for p in all_offers})==len(all_offers)
    # Two nonstacking pieces exercise allocation independently of bundle size.
    offers=[p for p in all_offers if p['category']//10==2 and TEMPLATE_BAG_GROUPS[p['template']]==27]
    request=struct.pack('>IIH',1,offers[0]['sku'],2)
    assert ed_purchase_request(request)==((offers[0]['sku'],2),)
    denied=session.handle(Event(0x202,kind=0x80f,payload=request),10)
    assert struct.unpack_from('>i',denied[0].payload)[0]!=0
    assert session.handle(Event(0x202,kind=0x80d,payload=struct.pack('>i',1)))==[ed_catalog_ack(all_offers)]
    assert len(ed_catalog_ack(offers).payload)==5+28*len(offers)
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('UPDATE reward_balances SET ed=500 WHERE uid=1001')
    event=Event(0x202,kind=0x80f,payload=request)
    first=session.handle(event,11);assert struct.unpack_from('>i',first[0].payload)[0]==0
    assert session.handle(event,11)==first
    with closing(sqlite3.connect(path)) as db,db:
        assert db.execute('SELECT ed FROM reward_balances').fetchone()[0]==400
        assert len(load_items(db))==2
        assert db.execute('SELECT COUNT(*) FROM shop_purchase_receipts').fetchone()[0]==1
    # A different payload may not reuse an existing transport operation.
    conflicting=struct.pack('>IIH',1,offers[1]['sku'],1)
    assert struct.unpack_from('>i',session.handle(Event(0x202,kind=0x80f,payload=conflicting),11)[0].payload)[0]!=0
    # Persisted receipts survive independent connections and concurrent retries.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:purchase(path,conflicting,'concurrent'),range(2)))
    assert results[0]==results[1]
    assert purchase(path,conflicting,'concurrent')==results[0]
    with closing(sqlite3.connect(path)) as db,db:
        assert db.execute('SELECT ed FROM reward_balances').fetchone()[0]==350
        assert len(load_items(db))==3
        before=list(db.iterdump())
    for bad in [request[:-1],request+b'\0',struct.pack('>IIH',1,0xffffffff,1),struct.pack('>IIH',1,offers[0]['sku'],36)]:
        try:purchase(path,bad,'bad')
        except ValueError:pass
        else:raise AssertionError('Invalid purchase accepted')
    with closing(sqlite3.connect(path)) as db,db:
        assert list(db.iterdump())==before
        db.execute('UPDATE reward_balances SET ed=5000 WHERE uid=1001')
        template=offers[0]['template']
        for slot in range(3,36):db.execute('INSERT INTO inventory_items VALUES (?,1001,?,0,1,27,?)',(2000000+slot,template,slot))
        db.commit();full=list(db.iterdump())
    try:purchase(path,request,'full')
    except ValueError:pass
    else:raise AssertionError('Full bag accepted purchase')
    with closing(sqlite3.connect(path)) as db,db:assert list(db.iterdump())==full
print('PASS: ED purchase debit+allocation+receipt, same-request retry, concurrent retry, conflict, malformed request, insufficient funds and full-bag rollback.')
