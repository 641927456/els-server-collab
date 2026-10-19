"""Complete bundle delivery, all-character accessories and storefront removals."""
import json
import sqlite3
import struct
import sys
import tempfile
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from els_server.domain.fashion_bundles import catalog as bundles, offers as bundle_offers, display_order
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS, TEMPLATE_BAG_GROUPS, fashion_catalog
from els_server.domain.shop_listing import NPC_MEDICINES
from els_server.storage.shop_state import catalog, purchase
from els_server.storage.inventory_state import InventoryState, grant_items
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.domain.fashion_state import move_fashion


def request(p, n=1):
    return struct.pack('>IIH', 1, 1200000000 + p['template'], n)


def dump(path):
    with closing(sqlite3.connect(path)) as db:
        return list(db.iterdump())


def denied(path, payload, op, uid=1001):
    before = dump(path)
    try:
        purchase(path, payload, op, uid)
    except ValueError:
        pass
    else:
        raise AssertionError('Disallowed purchase accepted')
    assert dump(path) == before


c = bundles()
assert len(c['offers']) == 3738
assert sum(p['kind'] == 'costume' for p in c['offers']) == 3550
assert sum(p['kind'] == 'accessory' for p in c['offers']) == 188
generic = next(p for p in c['offers'] if p['unit_type'] == 0 and len(p['contents_by_role']) == 15
               and all(ids == p['contents'] for ids in p['contents_by_role'].values()))
all_skus = {p['sku'] for p in catalog()}
assert not NPC_MEDICINES & {p['template'] for p in catalog()}
assert not {800000+p['template'] for p in fashion_catalog()['templates']} & all_skus
rank={t:n for n,t in enumerate(display_order())}
assert display_order()[0]==399234  # Last new series in the INT package resource.
assert rank[398261]<rank[204770] and rank[399234]<rank[250003246]
for role in range(1,16):
    products=bundle_offers(role)
    assert [rank[p['template']] for p in products]==sorted(rank[p['template']] for p in products)
    assert [p['template'] for p in catalog(role) if p['category'] in (52,53)]==[p['template'] for p in products]

# Independently cross-check against both complete native ice-preview resources.
ice = set()
for s in c['sources']:
    if 'IceHeaterPreView' in s['path']:
        d = json.loads((Path(__file__).resolve().parents[1] / s['path']).read_text(encoding='utf8'))
        ice.update(r['arguments'][2] for r in d['__symbolic_calls__'] if r['function'].endswith('.AddIceHeaterItemData'))
assert not ice & {t for p in c['offers'] for t in p['contents']}

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / 'bundles.sqlite3'
    account = LocalAccount(LocalState(path))
    account.enable_characters()
    owners = {n: account.characters.create('礼包角色' + str(n), n, 'create-' + str(n))['uid'] for n in range(1, 16)}
    for n, uid in owners.items():
        inv = InventoryState(path, uid)
        initial = inv.snapshot()['items']
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=500 WHERE uid=?', (uid,))
        specific = next(p for p in c['offers'] if p['kind'] == 'costume' and p['unit_type'] == n)
        visible = {p['template'] for p in catalog(n)}
        assert generic['template'] in visible and specific['template'] in visible
        assert all(p['template'] not in visible for p in c['offers'] if str(n) not in p['contents_by_role'])
        for index, p in enumerate((generic, specific)):
            reply = purchase(path, request(p), 'bundle-' + str(index), uid)
            before = inv.snapshot()
            assert purchase(path, request(p), 'bundle-' + str(index), uid) == reply
            assert inv.snapshot() == before
            expected = {i['template'] for i in initial} | set(generic['contents']) | (set(specific['contents']) if index else set())
            assert {i['template'] for i in before['items']} == expected
            assert before['balances']['ed'] == 500 - 50*(index+1)
            assert all(i['count'] == 1 for i in before['items'] if i['template'] in p['contents'])
        assert InventoryState(path, uid).snapshot() == before
        item = next(i for i in before['items'] if i['template'] in specific['contents'])
        equip_slot = FASHION_EQUIP_SLOTS[item['template']]
        old = next((i for i in before['items'] if (i['group'], i['slot']) == (9, equip_slot)), None)
        if old:
            bag = TEMPLATE_BAG_GROUPS[old['template']]
            slot = next(s for s in range(36) if not any(i['group'] == bag and i['slot'] == s for i in before['items']))
            move_fashion(path, struct.pack('>BiBiB', 9, equip_slot, bag, slot, 0), uid)
        move_fashion(path, struct.pack('>BiBiB', item['group'], item['slot'], 9, FASHION_EQUIP_SLOTS[item['template']], 0), uid)
        assert any(i['uid'] == item['uid'] and i['group'] == 9 for i in inv.snapshot()['items'])
        foreign = next(p for p in c['offers'] if p['kind'] == 'costume' and p['unit_type'] != n)
        denied(path, request(foreign), 'foreign', uid)
    assert InventoryState(path, 1001).snapshot()['items'] == []

    # A stale displayed SKU must not bypass removal; existing medicine survives.
    with closing(sqlite3.connect(path)) as db, db:
        grant_items(db, [dict(template=77000, metadata=2, group=6, quantity=3)])
    for t in NPC_MEDICINES:
        denied(path, struct.pack('>IIH', 1, 1200000000+t, 1), 'removed-' + str(t))
    for p in fashion_catalog()['templates']:
        denied(path, struct.pack('>IIH', 1, 800000+p['template'], 1), 'single-' + str(p['template']))
    assert InventoryState(path).snapshot()['items'][0]['count'] == 3

    uid = owners[1]
    p = next(p for p in c['offers'] if p['kind'] == 'costume' and p['unit_type'] == 1)
    denied(path, request(p, 36), 'expanded-limit', uid)
    # Failure after allocation and debit must undo every part of a set.
    before = InventoryState(path, uid).snapshot()
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TRIGGER bundle_receipt_failure BEFORE INSERT ON shop_purchase_receipts BEGIN SELECT RAISE(ABORT,'rollback'); END")
    sql_before = dump(path)
    try:
        purchase(path, request(p), 'sql-failure', uid)
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError('Receipt failure not exercised')
    assert dump(path) == sql_before and InventoryState(path, uid).snapshot() == before
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('DROP TRIGGER bundle_receipt_failure')
        # Leave fewer free slots than this costume needs, forcing partial allocation rollback.
        item = next(i for i in before['items'] if i['group'] in (7, 27))
        occupied = db.execute('SELECT COUNT(*) FROM inventory_items WHERE owner=? AND bag_group=?', (uid, item['group'])).fetchone()[0]
        grant_items(db, [dict(template=item['template'], metadata=item['metadata'], group=item['group'], quantity=35-occupied)], uid)
    denied(path, request(p), 'full-bag', uid)

print('PASS: 3738 bundles, zero ice rewards/medicine/single costumes in storefront; all 15 roles, universal accessories, full-set debit/delivery, equip/reload, retry, isolation and partial-allocation rollback.')
