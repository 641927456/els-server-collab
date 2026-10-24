"""GM shop additions: persisted offers, validation, purchase and removal."""
import sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain import shop_local_offers as shop
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.storage.inventory_state import InventoryState
from els_server.storage.reward_state import RewardState
from els_server.storage.shop_state import catalog,purchase

TEMPLATE=77000
assert TEMPLATE in VERIFIED_TEMPLATES
assert not any(p['template']==TEMPLATE for p in catalog()),'fixture template is already sold'
with tempfile.TemporaryDirectory() as directory:
    save=Path(directory)/'game.sqlite3';RewardState(save);inventory=InventoryState(save)
    shop.configure(Path(directory)/'local-shop-offers.json')
    assert shop.custom_offers()==()
    with closing(sqlite3.connect(save)) as db,db:db.execute('UPDATE reward_balances SET ed=100 WHERE uid=1001')
    added=shop.add(save,TEMPLATE,5,10,shop.DEFAULT_CATEGORY,'常用道具上架','op-add-1')
    assert (added['price'],added['quantity'],added['name'])==(5,10,'初级体力药水')
    assert shop.add(save,TEMPLATE,5,10,shop.DEFAULT_CATEGORY,'常用道具上架','op-add-1')==added
    try:shop.add(save,TEMPLATE,9,1,shop.DEFAULT_CATEGORY,'重复上架','op-add-2')
    except ValueError:pass
    else:raise AssertionError('Duplicate template accepted')
    try:shop.add(save,999999999,1,1,shop.DEFAULT_CATEGORY,'未验证道具','op-add-3')
    except ValueError:pass
    else:raise AssertionError('Unverified template accepted')
    offers=catalog();entry=next(p for p in offers if p['template']==TEMPLATE)
    assert (entry['sku'],entry['price'],entry['quantity'])==(added['sku'],5,10)
    assert shop.bulk_packs().get(TEMPLATE)==10
    assert shop.bulk_packs().get(shop.TEMPLATE)==shop.QUANTITY
    sold={p['template'] for p in catalog()}
    spare=next(t for t in sorted(VERIFIED_TEMPLATES) if t not in sold and t!=TEMPLATE)
    for price,quantity in ((shop.MAX_PRICE+1,1),(1,shop.MAX_QUANTITY+1)):
        try:shop.add(save,spare,price,quantity,shop.DEFAULT_CATEGORY,'超范围','op-range-'+str(price))
        except ValueError:pass
        else:raise AssertionError('Out-of-range offer accepted')
    reply=purchase(save,struct.pack('>IIH',1,entry['sku'],1),'gm-shop-buy')
    assert purchase(save,struct.pack('>IIH',1,entry['sku'],1),'gm-shop-buy')==reply
    saved=inventory.snapshot()
    assert saved['balances']['ed']==95
    assert [(i['count']) for i in saved['items'] if i['template']==TEMPLATE]==[10]
    shop.remove(save,TEMPLATE,'移出商城','op-remove-1')
    assert shop.custom_offers()==()
    assert not any(p['template']==TEMPLATE for p in catalog())
    try:shop.remove(save,TEMPLATE,'重复移出','op-remove-2')
    except ValueError:pass
    else:raise AssertionError('Missing offer removal accepted')
    assert inventory.snapshot()==saved
print('PASS: GM shop add/remove, duplicate and unverified rejection, pack purchase and idempotence.')
