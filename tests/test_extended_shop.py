"""Native catalog coverage, purchases, retry/rollback and accessory movement."""
import collections,json,sqlite3,struct,sys,tempfile
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.inventory_items import extended_shop_catalog,FASHION_EQUIP_SLOTS,TEMPLATE_BAG_GROUPS
from els_server.domain.fashion_state import move_fashion
from els_server.storage.inventory_state import InventoryState
from els_server.storage.reward_state import RewardState
from els_server.storage.shop_state import catalog,purchase
from els_server.protocol.shop_messages import ed_catalog_ack
from els_server.domain.bag_capacity import PRODUCT_GROUPS
from els_server.domain.skill_expansion import ORDINARY_SKU
from els_server.domain.fashion_bundles import catalog as bundle_catalog
from els_server.domain.shop_listing import include_extended,NPC_MEDICINES
from els_server.domain.shop_additions import offers as additional_offers
from els_server.domain.pet_support import offers as pet_support_offers
from els_server.domain.bank_memberships import offers as bank_offers
from els_server.domain.shop_local_offers import offers as local_shop_offers

offers=catalog();extended=extended_shop_catalog()['offers']
assert len(extended)==6328
assert len(offers)==272+1+len(bundle_catalog()['offers'])+sum(include_extended(p) for p in extended)+len(additional_offers())+len(pet_support_offers())+len(bank_offers())+len(local_shop_offers())
assert not NPC_MEDICINES & {p['template'] for p in offers}
assert not any(p['category']//10==1 for p in offers)
assert sum(p['sku']==ORDINARY_SKU for p in offers)==1
counts=collections.Counter(p['category']//10 for p in extended)
assert counts=={2:2264,3:569,4:8,5:361,6:36,9:3090}
assert {214410,214420,242310} <= {p['template'] for p in extended if p['category']==32}
assert {27,31,32,33,36,92,94,95} <= {p['category'] for p in extended}
assert not any(p['category']==96 for p in extended), 'System free portraits must remain unsold'
assert len({p['sku'] for p in offers})==len(offers)
assert all(0<p['sku']<2**31 for p in offers)
assert len(ed_catalog_ack(offers).payload)==5+28*len(offers)
# Immediate bag expansion is covered by test_bag_capacity; these rows test
# delivery of ordinary inventory products, not account/character entitlements.
representatives=[next(p for p in offers if p['category']//10==cat and p['template'] not in PRODUCT_GROUPS and p['sku']!=ORDINARY_SKU) for cat in (2,4,6,9)]
representatives.append(next(p for p in offers if p['category']//10==2 and TEMPLATE_BAG_GROUPS[p['template']]==7))
accessories=(representatives[0],representatives[-1])
for group in (3,21):
    available=[p for p in offers if TEMPLATE_BAG_GROUPS.get(p['template'])==group]
    if available:representatives.append(available[0])
representatives.extend(next(p for p in offers if p['category']==category) for category in (27,92,94,95))
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'shop.sqlite3';RewardState(path);inventory=InventoryState(path)
    with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE reward_balances SET ed=2000 WHERE uid=1001')
    for index,offer in enumerate(representatives):
        request=struct.pack('>IIH',1,offer['sku'],1)
        reply=purchase(path,request,'category-'+str(index))
        before=inventory.snapshot();assert purchase(path,request,'category-'+str(index))==reply
        assert inventory.snapshot()==before
        item=next(i for i in before['items'] if i['template']==offer['template'])
        assert item['count']==1 and item['group']==TEMPLATE_BAG_GROUPS[item['template']]
    assert inventory.snapshot()['balances']['ed']==2000-sum(p['price'] for p in representatives)
    assert InventoryState(path).snapshot()==inventory.snapshot()
    # Ordinary and premium avatar accessories retain their own bag on unequip.
    for offer in accessories:
        item=next(i for i in inventory.snapshot()['items'] if i['template']==offer['template'])
        slot=FASHION_EQUIP_SLOTS[item['template']]
        move_fashion(path,struct.pack('>BiBiB',item['group'],item['slot'],9,slot,0))
        saved=inventory.snapshot();equipped=next(i for i in saved['items'] if i['uid']==item['uid'])
        assert (equipped['group'],equipped['slot'])==(9,slot)
        wrong=27 if item['group']==7 else 7
        try:move_fashion(path,struct.pack('>BiBiB',9,slot,wrong,35,0))
        except ValueError:pass
        else:raise AssertionError('Wrong native accessory bag accepted')
        assert inventory.snapshot()==saved
        move_fashion(path,struct.pack('>BiBiB',9,slot,item['group'],item['slot'],0))
    before=inventory.snapshot()
    with closing(sqlite3.connect(path)) as db,db:
        db.execute("CREATE TRIGGER failed_receipt BEFORE INSERT ON shop_purchase_receipts BEGIN SELECT RAISE(ABORT,'rollback'); END")
    try:purchase(path,struct.pack('>IIH',1,representatives[0]['sku'],1),'failed')
    except sqlite3.IntegrityError:pass
    else:raise AssertionError('SQL failure not exercised')
    assert inventory.snapshot()==before
    try:purchase(path,struct.pack('>IIH',1,0x7fffffff,1),'forged')
    except ValueError:pass
    else:raise AssertionError('Unknown SKU accepted')
    assert inventory.snapshot()==before
print('PASS: requested subcategories, 6328 item proofs, free portraits excluded, durable purchases/retries/rollback, accessory equip and native bags.')
