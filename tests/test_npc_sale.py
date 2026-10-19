"""Merchant income, ownership, rollback and current-state replay in temp saves."""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.domain.npc_sale import unit_price
from els_server.protocol.npc_sale_messages import request, MERCHANT_XOR
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.npc_sale import sell


def payload(entries, merchant=10001, noise=b'abcd'):
    return (struct.pack('>I', len(noise)) + noise + struct.pack('>I', len(entries)) +
            b''.join(struct.pack('>Qi', *e) for e in entries) + struct.pack('>I', merchant ^ MERCHANT_XOR))


class SaleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'save.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()
        self.other = self.account.characters.create('SaleOther', 5, 'other')['uid']
        self.account.for_character(self.other)
        self.gear = self.grant(60100)

    def grant(self, template, count=1):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            return grant_items(db, [dict(template=template, metadata=VERIFIED_TEMPLATES[template],
                group=TEMPLATE_BAG_GROUPS[template], quantity=count)])[0]

    def items(self):
        with closing(sqlite3.connect(self.path)) as db: return load_items(db)

    def money(self):
        return LocalAccount(LocalState(self.path)).get_reward_balances()['ed']

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db: return list(db.iterdump())

    def test_full_equipment_sale_persists_and_forgets_attachments(self):
        from els_server.storage.equipment_enhancement import replace
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE'); replace(db, 1001, self.gear['uid'], 0, 3)
        before = self.money()
        events = sell(self.path, 1001, payload([(self.gear['uid'], 1)]), 'full')
        self.assertEqual(events[0].kind, 0xed)
        self.assertEqual(struct.unpack_from('>iQ', events[0].payload), (0, before+23520))
        self.assertEqual(self.money(), before+23520)
        self.assertNotIn(self.gear['uid'], {i['uid'] for i in self.items()})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertFalse(db.execute('SELECT 1 FROM equipment_enhancement WHERE item_uid=?', (self.gear['uid'],)).fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_partial_material_and_batch_prices(self):
        crystal = self.grant(701000, 20)
        before = self.money()
        sell(self.path, 1001, payload([(crystal['uid'], 7), (self.gear['uid'], 1)]), 'batch')
        self.assertEqual(self.money(), before+23520+3500)
        self.assertEqual(next(i for i in self.items() if i['uid']==crystal['uid'])['count'], 13)

    def test_hundred_item_batch_is_not_rejected_by_a_64k_assumption(self):
        from els_server.storage.bag_capacity import expand
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE'); expand(db, 1001, 200751, 9)
            more = grant_items(db, [dict(template=60100, metadata=1, group=1, quantity=99)])
        selected = [self.gear]+more; before = self.money()
        result = sell(self.path, 1001, payload([(i['uid'], 1) for i in selected]), 'hundred')
        self.assertGreater(len(result[0].payload), 64000)
        self.assertEqual(self.money(), before+100*23520)
        self.assertTrue({i['uid'] for i in selected}.isdisjoint(i['uid'] for i in self.items()))

    def test_durability_price_matches_float32_native_rule(self):
        cap = self.gear['durability']
        self.assertEqual(unit_price(dict(self.gear, durability=cap//2)), 11760)
        for item in (dict(self.gear, durability=0), dict(self.gear, group=9)):
            with self.assertRaises(ValueError):unit_price(item)

    def test_invalid_quantity_owner_and_mixed_batch_are_atomic(self):
        for owner, entries in ((self.other, [(self.gear['uid'], 1)]),
                (1001, [(self.gear['uid'], 2)]),
                (1001, [(self.gear['uid'], 1), (999999999, 1)])):
            before = self.dump()
            with self.assertRaises(ValueError):sell(self.path, owner, payload(entries), 'invalid')
            self.assertEqual(self.dump(), before)

    def test_lock_expiration_and_special_item_rejected(self):
        for item in (dict(self.gear, lock_until=2200000000),
                     dict(self.gear, expires_at=1000000000), self.grant(81021), self.grant(77420)):
            with self.assertRaises(ValueError):unit_price(item)

    def test_persisted_lock_and_expiration_reject_without_loss(self):
        from els_server.storage.item_locks import assign as lock
        from els_server.storage.item_expiration import assign as expire
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE'); lock(db, 1001, self.gear['uid'], 2200000000)
        before = self.dump()
        with self.assertRaises(ValueError):sell(self.path, 1001, payload([(self.gear['uid'], 1)]), 'locked')
        self.assertEqual(self.dump(), before)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM item_locks WHERE item_uid=?', (self.gear['uid'],))
            expire(db, 1001, self.gear['uid'], 1000000000)
        before = self.dump()
        with self.assertRaises(ValueError):sell(self.path, 1001, payload([(self.gear['uid'], 1)]), 'expired')
        self.assertEqual(self.dump(), before)

    def test_retry_never_recredits_or_replays_buyback_and_uses_current_slot(self):
        p = payload([(self.gear['uid'], 1)])
        sell(self.path, 1001, p, 'once')
        replacement = self.grant(30160)
        before = self.dump(); balance = self.money()
        retry = sell(self.path, 1001, payload([(self.gear['uid'], 1)], noise=b'new-noise'), 'once')
        self.assertEqual(struct.unpack('>iQII', retry[0].payload), (0, balance, 0, 0))
        self.assertEqual(retry[1].kind, 0x105)
        self.assertEqual(struct.unpack_from('>Q', retry[1].payload, 4)[0], replacement['uid'])
        self.assertEqual(self.dump(), before)
        with self.assertRaises(ValueError):sell(self.path, 1001, payload([(replacement['uid'], 1)]), 'once')

    def test_concurrent_duplicate_and_conflicting_sales_credit_once(self):
        p = payload([(self.gear['uid'], 1)]); before = self.money()
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _:sell(self.path, 1001, p, 'parallel'), range(2)))
        self.assertEqual(len(results), 2); self.assertEqual(self.money(), before+23520)
        with self.assertRaises(ValueError):sell(self.path, 1001, p, 'new')

    def test_two_distinct_competing_sales_cannot_sell_same_uid_twice(self):
        p = payload([(self.gear['uid'], 1)]); before = self.money()
        def attempt(operation):
            try:sell(self.path, 1001, p, operation); return True
            except ValueError:return False
        with ThreadPoolExecutor(2) as pool:
            result = list(pool.map(attempt, ('sale-a', 'sale-b')))
        self.assertEqual(sorted(result), [False, True]); self.assertEqual(self.money(), before+23520)

    def test_encoder_failure_and_balance_overflow_roll_back(self):
        p = payload([(self.gear['uid'], 1)]); before = self.dump()
        with patch('els_server.storage.npc_sale.acknowledgement', side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):sell(self.path, 1001, p, 'fail')
        self.assertEqual(self.dump(), before)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=? WHERE uid=1001', (2**63-1,))
        before = self.dump()
        with self.assertRaises(ValueError):sell(self.path, 1001, p, 'overflow')
        self.assertEqual(self.dump(), before)

    def test_request_shape_and_town_dispatch(self):
        p = payload([(self.gear['uid'], 1)])
        self.assertEqual(request(p), ([(self.gear['uid'], 1)], 10001))
        for bad in (b'', p+b'\0', payload([]), payload([(1, 0)]),
                    payload([(1, 1), (1, 1)]), payload([(1, 1)], 0),
                    payload([(1, 1)], noise=b'a'), payload([(1, 1)], noise=b'a'*17)):
            with self.assertRaises(ValueError):request(bad)
        session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
            client_build='dx11_260923', npc_slot_test=True, gate_test=True,
            population_test=True, clear_test=True, reward_test=True, item_test=True)
        session.role, session.phase = 'game', 'town_ready'; event = Event(0x202, kind=0xec, payload=p)
        for phase, seq in (('dungeon_active', 1), ('town_ready', 0), ('town_ready', None)):
            session.phase = phase; before = self.dump()
            self.assertEqual(struct.unpack_from('>i', session.handle(event, seq)[0].payload)[0], -1)
            self.assertEqual(self.dump(), before)
        self.assertEqual(session.handle(event, 2)[0].kind, 0xed)
        self.assertNotIn(self.gear['uid'], {i['uid'] for i in self.items()})


if __name__ == '__main__': unittest.main()
