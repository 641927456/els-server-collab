"""Exercise the new catalog through owned purchases, books and atomic rejects."""
import collections
import functools
import hashlib
import json
import sqlite3
import struct
import sys
import tempfile
import traceback
import time
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

W = Path(__file__).resolve().parent
R = W.parents[1]
C = W / 'candidate'
sys.dont_write_bytecode = True
sys.path[:0] = [str(C), str(R / 'tools'), str(R / 'tools/pylibs')]
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.storage import shop_state
from els_server.storage.inventory_state import load_items, grant_items
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS, VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.domain.fashion_state import move_fashion
from els_server.domain import character_custom as custom
from els_server.storage import character_custom as storage
from els_server.protocol import character_custom_messages as wire
from els_server.domain.shop_listing import ice_equipment
from els_server.domain.fashion_bundles import by_template, display_order
from els_server.game_data import client_data
from role_native_replay import Replay, IMAGE_SHA
from verify_role_progression_offline import check_unit

mode = sys.argv[1]
# Reuse the unchanged catalog construction during the bulk fixture sweep.
# Purchases and all economic/ownership checks still execute their real code.
shop_state.catalog = functools.lru_cache(maxsize=16, typed=True)(shop_state.catalog)
scope = json.loads((W / 'candidate-scope.json').read_bytes())
binding = json.loads((W / 'update-binding.json').read_bytes())
parent = Path(binding['parent_root'])
rows = []
checks = []
folder = tempfile.TemporaryDirectory(dir=W, prefix='business-' + mode + '-')
DB = Path(folder.name) / 'own.sqlite3'


def sql(query, args=()):
    with closing(sqlite3.connect(DB)) as db, db:
        return db.execute(query, args).fetchall()


def items(uid):
    with closing(sqlite3.connect(DB)) as db:
        return load_items(db, uid)


def dump():
    with closing(sqlite3.connect(DB)) as db:
        return tuple(db.iterdump())


def actor(role, index=0):
    aid = 10000 + role + 100 * index
    account = LocalAccount(LocalState(DB), account_id=aid)
    account.enable_characters()
    ch = account.characters.create('Shop' + str(role) + 'x' + str(index), role, 'create:' + str(aid))
    sql('UPDATE reward_balances SET ed=1000000 WHERE uid=?', (ch['uid'],))
    return dict(account_id=aid, uid=ch['uid'])


def request(t, count=1):
    return struct.pack('>IIH', 1, 1200000000 + t, count)


def check(name, value=True):
    assert value, name
    checks.append(name)


def denied(call):
    before = dump()
    try:
        call()
    except ValueError:
        pass
    else:
        raise AssertionError('Expected qualification rejection')
    assert dump() == before


def buy(t, owner, operation, expected):
    uid = owner['uid']
    before = items(uid)
    old_ids = {i['uid'] for i in before}
    ed = sql('SELECT ed FROM reward_balances WHERE uid=?', (uid,))[0][0]
    answer = shop_state.purchase(DB, request(t), operation, uid)
    new = [i for i in items(uid) if i['uid'] not in old_ids]
    assert collections.Counter(i['template'] for i in new) == collections.Counter(expected), (t, expected, new)
    assert all(i['count'] == 1 for i in new)
    assert sql('SELECT ed FROM reward_balances WHERE uid=?', (uid,)) == [(ed - 50,)]
    saved = (items(uid), sql('SELECT ed,revision FROM reward_balances WHERE uid=?', (uid,)), sql('SELECT count(*) FROM shop_purchase_receipts'))
    assert shop_state.purchase(DB, request(t), operation, uid) == answer
    assert saved == (items(uid), sql('SELECT ed,revision FROM reward_balances WHERE uid=?', (uid,)), sql('SELECT count(*) FROM shop_purchase_receipts'))
    return before, new


def clean_purchased(owner, before, new):
    # This is an owned disposable fixture reset, not a production item operation.
    with closing(sqlite3.connect(DB)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.executemany('DELETE FROM inventory_items WHERE uid=? AND owner=?', [(i['uid'], owner['uid']) for i in new])
    assert items(owner['uid']) == before


try:
    all_offers = {p['template']: p for p in shop_state.catalog()}
    expected = {p['template'] for p in scope['added_packages'] + scope['added_accessories']}
    check('every new package and accessory appears in the final catalog', expected <= set(all_offers))
    if mode == 'packages':
        actors = {n: actor(n) for n in range(1, 16)}
        checkpoint = W / 'business-packages-checkpoint.json'
        allowed = {p['template'] for p in scope['added_packages']}
        if checkpoint.exists():
            rows.extend(p for p in json.loads(checkpoint.read_bytes())['rows'] if p['template'] in allowed)
        previous = W / 'business-packages.json'
        if previous.exists():
            complete = {p['template']:p for p in rows}
            complete.update({p['template']:p for p in json.loads(previous.read_bytes())['rows'] if p['template'] in allowed})
            rows[:] = complete.values()
        passed = {p['template'] for p in rows}
        for n, p in enumerate(scope['added_packages']):
            if p['template'] in passed:
                continue
            role = int(next(iter(p['contents_by_role'])))
            owner = actors[role]
            before, new = buy(p['template'], owner, 'pack:' + str(p['template']), p['contents_by_role'][str(role)])
            clean_purchased(owner, before, new)
            rows.append(dict(template=p['template'], role=role, delivered=len(new), passed=True))
            if (n + 1) % 256 == 0:
                checkpoint.write_text(json.dumps(dict(rows=rows), ensure_ascii=False, indent=2), encoding='utf8')
                print('Bought, replayed, cold-read', n + 1, flush=True)
        check('every new complete/fan package purchases with exact one-each contents and50ED debit', len(rows) == len(scope['added_packages']))
    elif mode == 'accessories':
        actors = {n: actor(n) for n in range(1, 16)}
        replay = None
        for n, p in enumerate(scope['added_accessories']):
            raw = client_data().item(p['template'])['record']
            role = raw[210] or (10 if raw[8] & 4 else 1)
            owner = actors[role]
            uid = owner['uid']
            before, new = buy(p['template'], owner, 'acc:' + str(p['template']), [p['template']])
            item = new[0]
            bag = item['group'], item['slot']
            slot = FASHION_EQUIP_SLOTS[item['template']]
            move_fashion(DB, struct.pack('>BiBiB', *bag, 9, slot, 0), uid)
            assert any(i['uid'] == item['uid'] and i['group'] == 9 and i['slot'] == slot for i in items(uid))
            if n % 64 == 0:
                replay = Replay()
                check_unit(replay, Characters(DB, owner['account_id']).get(uid), items(uid))
            move_fashion(DB, struct.pack('>BiBiB', 9, slot, *bag, 0), uid)
            clean_purchased(owner, before, new)
            rows.append(dict(template=p['template'], role=role, equipment_slot=slot, passed=True))
            if (n + 1) % 256 == 0:
                print('Accessory bought/worn/unworn/cold', n + 1, flush=True)
        check('every new accessory purchase, wear, unwear, replay and cold inventory passed', len(rows) == len(scope['added_accessories']))
        check('original unit decoder accepts representative accessory slots and roles')
    elif mode == 'books':
        native_values = []
        prior = W / 'business-books.json'
        if not prior.exists():
            prior = W / 'business-books-failure.json'
        passed = {p['book']:p for p in json.loads(prior.read_bytes())['rows']} if prior.exists() else {}
        for n, t in enumerate(scope['added_books']):
            rule = custom.catalog()[t]
            if t in passed:
                rows.append(passed[t])
                continue
            role = rule['units'][0]
            owner = actor(role, n + 1)
            uid = owner['uid']
            p = next(p for p in scope['added_packages'] if t in p['contents'] and str(role) in p['contents_by_role'])
            before, new = buy(p['template'], owner, 'book-pack:' + str(t), p['contents_by_role'][str(role)])
            book = next(i for i in new if i['template'] == t)
            payload = struct.pack('>QQiiIB', book['uid'], rule['custom_id'], rule['type'], 0, 0, 0)
            result = storage.use_book(DB, uid, owner['account_id'], payload, 'book:' + str(t))
            assert not result['replayed'] and not any(i['uid'] == book['uid'] for i in items(uid))
            saved = dump()
            assert storage.use_book(DB, uid, owner['account_id'], payload, 'book:' + str(t))['replayed'] and dump() == saved
            for value in custom.book_values(rule):
                storage.select(DB, uid, owner['account_id'], wire.selection_map({rule['slot']: value}), 'select:' + str(t) + ':' + str(value['custom_id']))
                with closing(sqlite3.connect(DB)) as db:
                    assert storage.snapshot(db, uid)['selected'][rule['slot']] == value
                native_values.append(value)
            rows.append(dict(book=t, package=p['template'], role=role, registered=rule['custom_ids'], passed=True))
        native = Replay()
        root = native.alloc(0x1600)
        manager = root + 0xdc8
        flat = native.alloc(76 * 512)
        native.write(manager + 0x270, struct.pack('<QQQ', flat, flat, flat + 76 * 512))
        native.write(native.base + 0x4817e80, struct.pack('<Q', root))
        for value in native_values:
            raw = wire.registered(value).payload
            data = native.alloc(len(raw)); native.write(data, raw)
            buf = native.alloc(48); native.write(buf + 8, struct.pack('<QQQ', data, data + len(raw), data + len(raw)))
            stream = native.alloc(40)
            native.call(0x3b6d140, stream); native.call(0x3b6d1c0, stream, buf, 0)
            native.write(native.stack - 8 + 0x28, struct.pack('<Q', buf))
            assert native.call(0xbb7f30, 0, 0, 0, 0) & 255 == 1
            assert struct.unpack('<I', native.read(buf + 32, 4))[0] == len(raw)
        check('every newly admitted gift book purchases, registers, applies, replays and cold-reads', len(rows) == len(scope['added_books']))
        check('original4CD consumer accepts every new registered custom value')
    elif mode == 'native':
        for role in range(1, 16):
            owner = actor(role)
            uid = owner['uid']
            candidates = [p for p in scope['added_packages'] if 'EL★STAR2' in p['name']
                          and '稀有' in p['name'] and 'Track 2' not in p['name']
                          and '组合交换' not in p['name'] and str(role) in p['contents_by_role']]
            selected = [candidates[0]]
            if role == 10:
                selected = candidates  # Both Lu and Ciel retain their native side slots.
            native = Replay()
            for p in selected:
                before, new = buy(p['template'], owner, 'native:' + str(p['template']), p['contents_by_role'][str(role)])
                for item in new:
                    if item['template'] not in FASHION_EQUIP_SLOTS:
                        continue
                    slot = FASHION_EQUIP_SLOTS[item['template']]
                    bag = item['group'], item['slot']
                    move_fashion(DB, struct.pack('>BiBiB', *bag, 9, slot, 0), uid)
                    check_unit(native, Characters(DB, owner['account_id']).get(uid), items(uid))
                    move_fashion(DB, struct.pack('>BiBiB', 9, slot, *bag, 0), uid)
                clean_purchased(owner, before, new)
                rows.append(dict(role=role, package=p['template'], native_wear_unit_cold=True))
        check('all15roles and bothLu/Ciel sides wear newELSTAR2 sets and decode original cold units')
    elif mode in ('boundaries', 'capacity'):
        owner = actor(1)
        uid = owner['uid']
        p = next(p for p in scope['added_packages'] if p['template'] == 389998)
        if mode == 'boundaries':
            before, new = buy(p['template'], owner, 'once', p['contents_by_role']['1'])
            check('ELSTAR2 rare includes both hair variants, microphone and linked dance', len(new) == 9)
            clean_purchased(owner, before, new)
            foreign = next(p for p in scope['added_packages'] if p['unit_type'] == 2)
            denied(lambda: shop_state.purchase(DB, request(foreign['template']), 'foreign', uid))
            denied(lambda: shop_state.purchase(DB, request(p['template'], 2), 'once', uid))
            check('foreign character and conflicting replay rejected atomically')
            for name, callback in [('encode', patch('els_server.storage.shop_state.ed_purchase_ack', side_effect=RuntimeError('owned encoder failure')))]:
                saved = dump()
                with callback:
                    try: shop_state.purchase(DB, request(p['template']), name, uid)
                    except RuntimeError: pass
                    else: raise AssertionError('Encoding failure not exercised')
                check('response encoding failure rolls back items, money and receipt', dump() == saved)
            child = p['contents'][3]
            sql("CREATE TRIGGER own_member_failure BEFORE INSERT ON inventory_items WHEN NEW.template=" + str(child) + " BEGIN SELECT RAISE(ABORT,'own fixture'); END")
            saved = dump()
            try: shop_state.purchase(DB, request(p['template']), 'middle-failure', uid)
            except sqlite3.IntegrityError: pass
            else: raise AssertionError('Middle grant failure not exercised')
            check('middle member failure rolls back complete cart', dump() == saved)
            sql('DROP TRIGGER own_member_failure')
            sql('UPDATE reward_balances SET ed=49 WHERE uid=?', (uid,))
            denied(lambda: shop_state.purchase(DB, request(p['template']), 'poor', uid))
            sql('UPDATE reward_balances SET ed=1000000 WHERE uid=?', (uid,))
            check('insufficient balance changes nothing')
        from els_server.storage.bag_capacity import allowances
        group = TEMPLATE_BAG_GROUPS[p['contents'][0]]
        template = p['contents'][0]
        with closing(sqlite3.connect(DB)) as db, db:
            limit = allowances(db, uid)[group]
            used = sum(i['group'] == group for i in load_items(db, uid))
            remaining = limit - used - 1
            while remaining:
                count = min(remaining, 36)
                grant_items(db, [dict(template=template, metadata=VERIFIED_TEMPLATES[template], group=group, quantity=1)
                                 for _ in range(count)], uid)
                remaining -= count
        denied(lambda: shop_state.purchase(DB, request(p['template']), 'full', uid))
        check('partial allocation followed by bag full leaves no economic increment')
        for role in range(1, 16):
            visible = {p['template'] for p in shop_state.catalog(role)}
            assert all((p['template'] in visible) == (str(role) in p['contents_by_role']) for p in scope['added_packages'])
            assert all((p['template'] in visible) == (p['role'] in (0, role)) for p in scope['added_accessories'])
        check('all15role catalogs apply package/accessory eligibility')
        true_ice = {r['template'] for r in json.loads((C / 'analysis/client-6c6b5180/role-ice-catalog.json').read_bytes())['rewards']}
        check('true ice equipment remains excluded', true_ice <= ice_equipment() and not true_ice & set(all_offers))
        for f in ['els_server/data/fashion_singles.json', 'els_server/data/fashion_singles.manifest.json']:
            assert (C / f).read_bytes() == (parent / f).read_bytes()
        check('ordinary standalone fashion selection and manifest remain byte-identical')
        old_order = json.loads((parent / 'analysis/shop-listing-20261015/bundle-order.json').read_bytes())['templates']
        old_set = set(old_order)
        check('all previously listed bundle ordering preserved', [t for t in display_order() if t in old_set] == old_order)
        assert all(p['template'] not in all_offers for p in scope['held'])
        check('unqualified candidates remain unavailable')
    else:
        raise ValueError(mode)
except BaseException as error:
    result = dict(ok=False, mode=mode, checks=checks, rows=rows,
                  error=dict(type=type(error).__name__, message=str(error), traceback=traceback.format_exc()), fixture=str(DB))
    failed = W / ('business-' + mode + '-failure.json')
    if failed.exists():
        failed = W / ('business-' + mode + '-failure-' + str(time.time_ns()) + '.json')
    failed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(result['error']['traceback'])
    folder.cleanup()
    raise
else:
    result = dict(ok=True, mode=mode, checks=checks, rows=rows, native_image_sha256=IMAGE_SHA,
                  live_process=False, natural_GUI=False, formal_database_written=False)
    (W / ('business-' + mode + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    folder.cleanup()
    print(json.dumps(dict(ok=True, mode=mode, cases=len(rows), checks=checks), ensure_ascii=False))
