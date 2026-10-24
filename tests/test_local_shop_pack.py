"""Local bulk pack: 1 ED buys 1000 El resonance potions, split by stack limit."""
import sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.shop_local_offers import PRICE,QUANTITY,SKU,TEMPLATE
from els_server.storage.inventory_state import InventoryState
from els_server.storage.reward_state import RewardState
from els_server.storage.shop_state import catalog,purchase

with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'shop.sqlite3';RewardState(path);inventory=InventoryState(path)
    offer=next(p for p in catalog(1) if p['sku']==SKU)
    assert (offer['template'],offer['price'],offer['quantity'])==(TEMPLATE,PRICE,QUANTITY)==(135948,1,1000)
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('UPDATE reward_balances SET ed=3 WHERE uid=1001')
    request=struct.pack('>IIH',1,SKU,1)
    reply=purchase(path,request,'local-pack')
    assert purchase(path,request,'local-pack')==reply
    saved=inventory.snapshot()
    assert saved['balances']['ed']==2
    stacks=[i for i in saved['items'] if i['template']==TEMPLATE]
    assert sum(i['count'] for i in stacks)==QUANTITY
    assert len(stacks)==2 and sorted(i['count'] for i in stacks)==[1,999]
    # A single request may only contain one bulk pack.
    other=next(p['sku'] for p in catalog(1) if p['quantity']==1)
    mixed=struct.pack('>IIHIH',2,SKU,1,other,1)
    for payload in (struct.pack('>IIH',1,SKU,2),mixed):
        try:purchase(path,payload,'two-packs')
        except ValueError:pass
        else:raise AssertionError('Bulk pack quantity accepted')
        assert inventory.snapshot()==saved
print('PASS: local bulk pack price/quantity, stack split, retry idempotence and single-pack bound.')
