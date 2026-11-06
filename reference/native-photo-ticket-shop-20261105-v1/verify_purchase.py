"""Owned catalog -> 50 ED purchase -> ticket use -> cold read, using shared SQL."""
from pathlib import Path
from contextlib import closing
import ctypes
import hashlib
import json
import sqlite3
import struct
import sys
import tempfile
import time
import traceback

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'performance-integration-v2/test-full-source'
sys.dont_write_bytecode = True
ctypes.WinDLL(str(BASE / 'python/sqlite3.dll'))
sys.path[:0] = [str(BASE), str(BASE / 'vendor')]
import els_server.domain
els_server.domain.__path__.insert(0, str(HERE / 'candidate/els_server/domain'))
from els_server.domain.local_session import LocalAccount
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from els_server.storage import shop_state, photo_zone_state
from els_server.protocol import shop_messages


def main():
    report = dict(passed=False, cases=[], production_database_access=False,
        natural_GUI=False, source_sha256=hashlib.sha256(
            (HERE/'candidate/els_server/domain/shop_additions.py').read_bytes()).hexdigest())
    try:
        with tempfile.TemporaryDirectory(prefix='owned-ticket-shop-', dir=HERE) as temporary:
            path = Path(temporary) / 'own.sqlite3'
            prepare(path)
            roster = Characters(path, 1)
            uid = roster.create('OwnPhotoBuy', 1, 'owned-photo-buy-create')['uid']
            local = LocalAccount(LocalState(path, uid), account_id=1)
            local.enable_characters(characters=roster)
            local.get_inventory_snapshot()
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('UPDATE reward_balances SET ed=100 WHERE uid=?', (uid,))

            def dump():
                with closing(sqlite3.connect(path)) as db:
                    return list(db.iterdump())

            def read():
                with closing(sqlite3.connect(path)) as db:
                    return (db.execute('SELECT ed FROM reward_balances WHERE uid=?', (uid,)).fetchone()[0],
                            load_items(db, uid))

            selected = [p for p in shop_state.catalog(1) if p['template'] == 288494]
            assert len(selected) == 1
            offer = selected[0]
            assert (offer['sku'], offer['price'], offer['quantity'], offer['category']) == (1200288494,50,1,41)
            catalog_wire = shop_messages.ed_catalog_ack(shop_state.quantity_catalog(1))
            expected = struct.pack('>Iiiiiii',1200288494,288494,41,50,0,1,0)
            assert catalog_wire.payload.count(expected) == 1
            payload = struct.pack('>IIH',1,offer['sku'],1)
            response = shop_state.purchase(path,payload,'owned-ticket-buy',uid)
            ed, items = read()
            tickets = [i for i in items if i['template'] == 288494]
            assert ed == 50 and len(tickets) == 1 and tickets[0]['count'] == 1
            before = dump()
            assert shop_state.purchase(path,payload,'owned-ticket-buy',uid) == response
            assert dump() == before
            report['cases'].append(dict(name='native_catalog_and_purchase',price_ed=50,quantity=1,
                replay_preserves_ed_and_item_uid=True))

            photo_zone_state.use(path,uid,1,struct.pack('>QH',tickets[0]['uid'],1052),
                'owned-shop-photo-unlock',lambda db:photo_zone_state.require_owner(db,uid,1))
            with closing(sqlite3.connect(path)) as db:
                assert 1052 in photo_zone_state.snapshot(db,uid,1)
            assert not [i for i in read()[1] if i['template'] == 288494]
            before = dump()
            retried = shop_state.purchase(path,payload,'owned-ticket-buy',uid)
            assert struct.unpack_from('>Q',retried,len(retried)-8)[0] == 50
            assert dump() == before
            with closing(sqlite3.connect(path)) as db:
                assert db.execute('SELECT COUNT(*) FROM shop_purchase_receipts').fetchone()[0] == 1
                assert 1052 in photo_zone_state.snapshot(db,uid,1)
            report['cases'].append(dict(name='purchased_ticket_consumption_and_cold_read',
                unlocked_world=1052,replay_after_use_does_not_restore_consumed_ticket=True))

            with closing(sqlite3.connect(path)) as db, db:
                db.execute('UPDATE reward_balances SET ed=49 WHERE uid=?',(uid,))
            before = dump()
            try:
                shop_state.purchase(path,payload,'owned-ticket-insufficient',uid)
                raise AssertionError('49 ED was admitted')
            except ValueError as error:
                assert str(error) == 'Insufficient ED'
            assert dump() == before
            report['cases'].append(dict(name='insufficient_ed',ed=49,sql_unchanged=True))
        report['passed'] = True
    except BaseException:
        report['error'] = traceback.format_exc()
    target = HERE / ('purchase-' + str(time.time_ns()) + '.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=report['passed'],cases=len(report['cases']),report=str(target),
        error=report.get('error')),ensure_ascii=False))
    return not report['passed']

if __name__ == '__main__':
    raise SystemExit(main())
