"""Cross-role storefront and economic isolation, including rejected stale SKUs."""
import sys,json,sqlite3,struct,tempfile
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.ice_rules import role_pools,series_pools
from els_server.domain.inventory_items import native_ice_catalog,role_ice_catalog
from els_server.storage.shop_state import catalog,home_lists,purchase
from els_server.storage.ice_state import draw
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.protocol.protocol_codec import Event
from els_server.protocol.shop_messages import ed_catalog_ack
machines={p['template'] for p in native_ice_catalog()['offers']}
rewards={p['template']:p for p in role_ice_catalog()['rewards']}
for role in range(1,16):
    allowed=set(role_pools(role));shown={p['template'] for p in catalog(role)}&machines
    assert shown==allowed
    assert all(set(ids)&machines<=allowed for ids in home_lists(role))
    for pool in series_pools(role).values():
        for reward,_ in pool:
            # Native compact template's role field must be common or matching.
            assert bytes.fromhex(rewards[reward]['record_hex'])[210] in (0,role)
wrong=next(iter(set(role_pools(12))-set(role_pools(5))))
common=800000
assert role_pools(1)[common]!=role_pools(5)[common]
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'save.sqlite3';root=LocalAccount(LocalState(path));root.enable_characters()
    eve=root.characters.create('EveTest',5,'create');account=root.for_character(eve['uid'])
    initial=account.get_inventory_snapshot()['items']
    session=LocalSession(account);session.role='game';session.phase='town_ready';session.shop_test=True;session.ice_test=True
    assert session.handle(Event(0x202,kind=0x80d,payload=struct.pack('>i',1)))==[ed_catalog_ack(catalog(5))]
    with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE reward_balances SET ed=300 WHERE uid=?',(eve['uid'],))
    def buy(template):
        offer=next(p for p in catalog() if p['template']==template)
        return struct.pack('>IIH',1,offer['sku'],1)
    try:purchase(path,buy(wrong),'wrong',eve['uid'])
    except ValueError:pass
    else:raise AssertionError('Foreign character SKU accepted')
    with closing(sqlite3.connect(path)) as db,db:
        assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(eve['uid'],)).fetchone()[0]==300
        assert load_items(db,eve['uid'])==initial
    purchase(path,buy(common),'valid',eve['uid'])
    with closing(sqlite3.connect(path)) as db,db:item=load_items(db,eve['uid'])[0]
    use=struct.pack('>QBBBIi',item['uid'],0,0,0,0,0)
    answer=draw(path,use,'draw',uid=eve['uid'],randbelow=lambda n:0)
    assert draw(path,use,'draw',uid=eve['uid'],randbelow=lambda n:1/0)==answer
    with closing(sqlite3.connect(path)) as db,db:
        items=load_items(db,eve['uid']);assert any(i['template']==role_pools(5)[common][0][0] for i in items)
        assert not load_items(db,1001)
        # Previously purchased foreign machines remain in the bag, but cannot
        # consume a stack or produce another character's equipment.
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES
        foreign=grant_items(db,[dict(template=wrong,metadata=VERIFIED_TEMPLATES[wrong],group=4,quantity=1)],eve['uid'])[0]
    try:draw(path,struct.pack('>QBBBIi',foreign['uid'],0,0,0,0,0),'foreign',uid=eve['uid'])
    except ValueError:pass
    else:raise AssertionError('Foreign machine drawn')
    with closing(sqlite3.connect(path)) as db,db:assert any(x['uid']==foreign['uid'] for x in load_items(db,eve['uid']))
print('PASS: all 15 role catalogs/home lists, native reward roles, Eve draw and retry, foreign purchase/draw rollback, owner isolation.')
