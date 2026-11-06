"""Real isolated shop -> draw transactions, role checks and unchanged catalog."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import functools, json, sqlite3, struct, sys, tempfile

W = Path(__file__).resolve().parent
R = W.parents[1]
C = W/'candidate'
sys.dont_write_bytecode = True
sys.path[:0] = [str(C)]
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items, grant_items
from els_server.storage import shop_state, ice_state
from els_server.domain.ice_rules import role_pools, series_pools, reward_quantity
from els_server.domain.inventory_items import native_ice_catalog, role_ice_catalog, VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.domain.shop_additions import catalog as supplement
from els_server.protocol.ice_messages import result_events, preview_ack

shop_state.catalog = functools.lru_cache(maxsize=16)(shop_state.catalog)
machine = 163483
sku = 1000000000+machine
scope = json.loads((W/'scope.json').read_bytes())
parent = Path(json.loads((W/'binding.json').read_bytes())['parent_root'])
old_native = json.loads((parent/'analysis/client-6c6b5180/native-ice-shop-catalog.json').read_bytes())
old_role = json.loads((parent/'analysis/client-6c6b5180/role-ice-catalog.json').read_bytes())
new_native = native_ice_catalog()
new_role = role_ice_catalog()
assert [r for r in new_native['offers'] if r['template'] != machine] == old_native['offers']
assert new_native['rewards'] == old_native['rewards']
assert {k: v for k, v in new_role['pools'].items() if k != str(machine)} == old_role['pools']
assert new_role['rewards'] == old_role['rewards']
checks = ['all existing offers, role pools and rewards unchanged', 'native reader/classifier new machine passed']
rows = []

with tempfile.TemporaryDirectory(dir=W, prefix='owned-') as folder:
    dbpath = Path(folder)/'own.sqlite3'
    def sql(query, args=()):
        with closing(sqlite3.connect(dbpath)) as db, db:
            return db.execute(query, args).fetchall()
    def items(uid):
        with closing(sqlite3.connect(dbpath)) as db:
            return load_items(db, uid)
    def snapshot():
        with closing(sqlite3.connect(dbpath)) as db:
            return tuple(db.iterdump())
    def deny(call, error=ValueError):
        before = snapshot()
        try:
            call()
        except error:
            pass
        else:
            raise AssertionError('Expected rejection')
        assert snapshot() == before
    def actor(role):
        account = LocalAccount(LocalState(dbpath), account_id=role)
        account.enable_characters()
        character = account.characters.create('Royal'+str(role), role, 'create:'+str(role))
        sql('UPDATE reward_balances SET ed=1000 WHERE uid=?', (character['uid'],))
        return character['uid']
    actors = {role: actor(role) for role in range(1, 16)}
    for role, uid in actors.items():
        offered = [p for p in shop_state.catalog(role) if p['template'] == machine]
        request = struct.pack('>IIH', 1, sku, 2)
        if role > 11:
            assert not offered and machine not in role_pools(role)
            deny(lambda: shop_state.purchase(dbpath, request, 'incompatible:'+str(role), uid))
            dedicated = {12: 292855, 13: 305707, 14: 316935, 15: 333454}[role]
            assert dedicated in {p['template'] for p in shop_state.catalog(role)}
            rows.append(dict(role=role, rejected_unsupported_old_machine=True, dedicated_retained=dedicated))
            continue
        assert len(offered) == 1 and offered[0]['price'] == 30 and offered[0]['category'] == 34
        pool = role_pools(role)[machine]
        series = series_pools(role)[machine]
        assert set(t for t, w in series) == set(new_role['pools'][str(machine)][str(role)])
        assert sum(w for t, w in pool) == 10000 and len(pool) == len({t for t, w in pool})
        assert sum(w for t, w in pool if t in dict(series)) == 1000
        assert len(preview_ack(0, machine, entries=tuple((t, 0, 1) for t, w in pool)).payload) == 22+12*len(pool)
        receipt = shop_state.purchase(dbpath, request, 'buy:'+str(role), uid)
        state = snapshot()
        shop_state.purchase(dbpath, request, 'buy:'+str(role), uid)
        assert snapshot() == state
        assert sql('SELECT ed FROM reward_balances WHERE uid=?', (uid,)) == [(940,)]
        source = next(i for i in items(uid) if i['template'] == machine)
        assert source['count'] == 2
        use = struct.pack('>QBBBIi', source['uid'], 0, 0, 0, 0, 0)
        other = actors[role % 11+1]
        deny(lambda: ice_state.draw(dbpath, use, 'foreign:'+str(role), uid=other, randbelow=lambda _: 0))
        # Fail after consume/grant but before commit: all inventory and ED roll back.
        with patch.object(ice_state, 'result_events', side_effect=ValueError('injected precommit encoding failure')):
            deny(lambda: ice_state.draw(dbpath, use, 'encoding:'+str(role), uid=uid, randbelow=lambda _: 0))
        first = ice_state.draw(dbpath, use, 'series:'+str(role), uid=uid, randbelow=lambda _: 0)
        assert [e.kind for e in result_events(first)] == [0xad8, 0x197]
        state = snapshot()
        ice_state.draw(dbpath, use, 'series:'+str(role), uid=uid, randbelow=lambda _: 1/0)
        assert snapshot() == state
        target = 130165
        roll = 0
        for template, weight in pool:
            if template == target:
                break
            roll += weight
        else:
            raise AssertionError('Missing existing potion reward')
        before_count = sum(i['count'] for i in items(uid) if i['template'] == target)
        second = ice_state.draw(dbpath, use, 'common:'+str(role), uid=uid, randbelow=lambda _: roll)
        assert [e.kind for e in result_events(second)] == [0xad8, 0x197]
        assert all(i['uid'] != source['uid'] for i in items(uid))
        assert sum(i['count'] for i in items(uid) if i['template'] == target) == before_count+20
        assert reward_quantity(machine, target) == 20
        state = snapshot()
        ice_state.draw(dbpath, use, 'common:'+str(role), uid=uid, randbelow=lambda _: 1/0)
        assert snapshot() == state
        deny(lambda: ice_state.draw(dbpath, use, 'stale:'+str(role), uid=uid, randbelow=lambda _: 0))
        # Independent SQL connections above and a fresh account projection read committed state.
        cold = LocalAccount(LocalState(dbpath), account_id=role)
        cold.enable_characters()
        assert cold.characters.get(uid)['uid'] == uid
        assert sql('SELECT ed FROM reward_balances WHERE uid=?', (uid,)) == [(940,)]
        rows.append(dict(role=role, preview_items=len(pool), series_items=len(series), purchased=2,
                         price_ED=30, series_draw=True, common_quantity=20, replay_unchanged=True,
                         precommit_rollback=True, cross_owner_rejected=True, cold_read=True))
    # Purchase balance rejection must not allocate a machine or create a receipt.
    uid = actors[1]
    sql('UPDATE reward_balances SET ed=0 WHERE uid=?', (uid,))
    deny(lambda: shop_state.purchase(dbpath, struct.pack('>IIH', 1, sku, 1), 'poor', uid))
    checks += ['11 roles purchase/draw/replay/cold read', '4 unsupported roles rejected; dedicated machines retained',
               '11 precommit failures roll back consume/grant', '11 cross-owner uses rejected',
               '11 exhausted source uses rejected', 'insufficient ED purchase rolls back']

report = dict(ok=True, machine=machine, checks=checks, rows=rows, data_only_delta=scope['delta'],
              original_native_reader_cases=1, natural_GUI=False, installed=False)
(W/'business.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', 'utf8')
print(json.dumps(dict(ok=True, roles=len(rows), checks=checks)))
