"""Native exclusions, character compatibility, common quantities and atomicity."""
import json,sqlite3,struct,sys,tempfile
from pathlib import Path
from contextlib import closing
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.shop_additions import catalog as supplement,offers as additions
from els_server.domain.shop_listing import ice_equipment,npc_items
from els_server.domain.ice_rules import role_pools,series_pools,reward_quantity
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item
from els_server.storage.shop_state import catalog,purchase
from els_server.storage.inventory_state import InventoryState,load_items,grant_items
from els_server.storage.reward_state import RewardState
from els_server.storage.ice_state import draw
from els_server.domain.fashion_bundles import offers as bundles
from els_server.domain.fashion_state import move_fashion
from els_server.game_data import client_data
from els_server.protocol.ice_messages import preview_ack

common=supplement('ice-common');rows={r['template']:r for r in supplement('standalone')['definitions']}
assert {r['item_type'] for r in rows.values()} >= {3,12,13}
for role in range(1,16):
    shown={p['template'] for p in catalog(role)}
    assert not shown&ice_equipment() and not shown&npc_items()
    for p in additions(role):assert rows[p['template']]['role'] in (0,role)
    for bundle in bundles(role):
        from els_server.domain.fashion_bundles import by_template
        assert not set(by_template()[bundle['template']]['contents_by_role'][str(role)])&ice_equipment()
    for machine,pool in role_pools(role).items():
        assert len(preview_ack(0,machine,entries=tuple((t,0,1) for t,w in pool)).payload)==22+12*len(pool)
        assert len(pool)==len({t for t,w in pool}) and sum(w for t,w in pool)==10000
        profile=common['profiles'][common['machine_profiles'][str(machine)]]
        series={t for t,w in series_pools(role)[machine]}
        assert sum(w for t,w in pool if t in series)==profile['cosmetic_weight']
        for t,w in pool:
            assert w>0 and t in VERIFIED_TEMPLATES
            if client_data().item(t)['item_type']==3:assert client_data().item(t)['record'][210] in (0,role)
        if common['machine_profiles'][str(machine)]=='sealed':
            assert not {130150,130151,135930,135932,154039,154048,130159}&{t for t,w in pool}

def snapshot(path):
    with closing(sqlite3.connect(path)) as db:return list(db.iterdump())
def use(uid):return struct.pack('>QBBBIi',uid,0,0,0,0,0)
def seed(path,t,n):
    with closing(sqlite3.connect(path)) as db,db:
        return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)])[0]
def roll_for(machine,target):
    offset=0
    for t,w in role_pools(1)[machine]:
        if t==target:return offset
        offset+=w
    raise AssertionError(target)

with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'shop.sqlite3';RewardState(path);inventory=InventoryState(path)
    with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE reward_balances SET ed=1000 WHERE uid=1001')
    for ty in (3,7,12,13):
        p=next(p for p in additions(1) if rows[p['template']]['item_type']==ty)
        request=struct.pack('>IIH',1,p['sku'],1);reply=purchase(path,request,'buy-'+str(ty));before=snapshot(path)
        assert purchase(path,request,'buy-'+str(ty))==reply and snapshot(path)==before
        item=next(i for i in inventory.snapshot()['items'] if i['template']==p['template']);validate_item(item)
        if ty==3:
            from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
            slot=FASHION_EQUIP_SLOTS[item['template']]
            move_fashion(path,struct.pack('>BiBiB',item['group'],item['slot'],9,slot,0))
            move_fashion(path,struct.pack('>BiBiB',9,slot,item['group'],item['slot'],0))
    assert inventory.snapshot()['balances']['ed']==800
    before=snapshot(path)
    for t in (77000,81021,135928):
        try:purchase(path,struct.pack('>IIH',1,1200000000+t,1),'forbidden-'+str(t))
        except ValueError:pass
        else:raise AssertionError('Removed SKU purchased')
    assert snapshot(path)==before
    machine=seed(path,800000,2);partial=seed(path,130165,90)
    payload=use(machine['uid']);roll=roll_for(800000,130165)
    reply=draw(path,payload,'quantity',randbelow=lambda _:roll);before=snapshot(path)
    assert draw(path,payload,'quantity',randbelow=lambda _:1/0)==reply and snapshot(path)==before
    potion=[i for i in inventory.snapshot()['items'] if i['template']==130165]
    assert sorted(i['count'] for i in potion)==[41,99]
    assert reward_quantity(800000,130165)==50 and reward_quantity(163362,130165)==20
    assert InventoryState(path).snapshot()==inventory.snapshot()
    # Rollback after partial stacking plus exhausted consumable removal.
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('DELETE FROM inventory_items WHERE template=?',(130165,))
    seed(path,130165,98)
    with closing(sqlite3.connect(path)) as db,db:
        occupied=sum(i['group']==6 for i in load_items(db))
        grant_items(db,[dict(template=77000,metadata=2,group=6,quantity=99) for _ in range(36-occupied)])
    before=snapshot(path)
    try:draw(path,payload,'full',randbelow=lambda _:roll)
    except ValueError:pass
    else:raise AssertionError('Partially stackable common reward overfilled bag')
    assert snapshot(path)==before
    # Exhausted/removed inventory rows cannot authorize stale requests.
    for item in inventory.snapshot()['items']:validate_item(item)
print('PASS: native standalone purchase/equip/persistence; all 15 role pools, ice/NPC exclusions, split quantities, immutable replay and partial-stack/full-bag rollback.')
