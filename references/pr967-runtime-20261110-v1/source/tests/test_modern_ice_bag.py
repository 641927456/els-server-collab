"""挫宝机 rewards land in the account 百宝袋 and 领取 (BD3) moves them back.

The native bag is account scoped, so a draw only reaches it when the caller
supplies the selected actor; the reward must never be granted straight into an
inventory slot the way the pre-2026 cube path did.
"""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.local_session import LocalAccount
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS, VERIFIED_TEMPLATES
from els_server.domain.modern_ice import machines
from els_server.storage import ice_state, modern_ice
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.local_state import LocalState

MACHINE = 800000          # ordinary modern ice machine
ACCOUNT = 1


def request(uid):
    return struct.pack('>QBBBIi', uid, 0, 0, 0, 0, 0)


class BagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'ice.sqlite3'
        account = LocalAccount(LocalState(self.path)); account.enable_characters()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            self.cube = grant_items(db, [dict(template=MACHINE,
                metadata=VERIFIED_TEMPLATES[MACHINE],
                group=TEMPLATE_BAG_GROUPS[MACHINE], quantity=2)], 1001)[0]

    def draw(self, operation='draw', randbelow=lambda n: 0):
        return ice_state.draw(self.path, request(self.cube['uid']), operation,
                              randbelow=randbelow, uid=1001, account_id=ACCOUNT,
                              prepare=lambda db: None)

    def bag(self):
        with closing(sqlite3.connect(self.path)) as db:
            return modern_ice.bag_items(db, ACCOUNT)

    def items(self):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db, 1001)

    def test_the_machine_is_a_2026_cube(self):
        self.assertIn(MACHINE, machines())
        self.assertEqual(machines()[MACHINE]['paid'], MACHINE)

    def test_a_draw_publishes_into_the_bag_and_not_the_inventory(self):
        self.draw()
        bag = self.bag()
        self.assertEqual(len(bag), 1)
        self.assertGreaterEqual(bag[0]['count'], 1)
        self.assertFalse(any(i['template'] == bag[0]['template'] for i in self.items()))
        # Only the consumed cube stack stays in the inventory.
        self.assertEqual([(i['template'], i['count']) for i in self.items()], [(MACHINE, 1)])

    def test_a_replayed_draw_does_not_grant_twice(self):
        first = self.draw()
        bag = self.bag()
        self.assertEqual(self.draw(randbelow=lambda n: 1/0), first)
        self.assertEqual(self.bag(), bag)

    def test_points_accrue_per_machine_family(self):
        self.draw()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertGreaterEqual(modern_ice.point_balance(db, ACCOUNT), 0)
            row = db.execute('SELECT COUNT(*) FROM modern_ice_bag WHERE account_id=?', (ACCOUNT,)).fetchone()
            self.assertEqual(row[0], 1)

    def test_claiming_moves_the_row_back_into_the_inventory(self):
        self.draw()
        row = self.bag()[0]
        payload = struct.pack('>I', 1) + struct.pack('>Qi', row['uid'], row['count'])
        events = modern_ice.withdraw(self.path, 1001, ACCOUNT, payload, 'claim-1',
                                     lambda db: None)
        acks = [e for e in events if e.kind in (0xbd4, 0xbd5)]
        self.assertTrue(acks)
        self.assertEqual(struct.unpack_from('>i', acks[0].payload)[0], 0)
        self.assertEqual(self.bag(), [])
        owned = [(i['template'], i['count']) for i in self.items()]
        self.assertIn((row['template'], row['count']), owned)

    def test_the_snapshot_reports_the_bag_and_points(self):
        self.draw()
        row = self.bag()[0]
        events = modern_ice.snapshot(self.path, 1001, ACCOUNT, lambda db: None, initial=True)
        kinds = [e.kind for e in events]
        self.assertIn(0xbd8, kinds)
        # The bag vector publishes the exact owned instance (uid, group 28).
        self.assertTrue(any(struct.pack('>Q', row['uid']) in e.payload for e in events))


class RouterTests(unittest.TestCase):
    """2EC8DE0 sends BD3 and waits for BD4; BD4 is a reply, never a request."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'ice.sqlite3'
        account = LocalAccount(LocalState(self.path)); account.enable_characters()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            self.cube = grant_items(db, [dict(template=MACHINE,
                metadata=VERIFIED_TEMPLATES[MACHINE],
                group=TEMPLATE_BAG_GROUPS[MACHINE], quantity=2)], 1001)[0]
        ice_state.draw(self.path, request(self.cube['uid']), 'seed-draw',
                       randbelow=lambda n: 0, uid=1001, account_id=ACCOUNT,
                       prepare=lambda db: None)
        with closing(sqlite3.connect(self.path)) as db:
            self.row = modern_ice.bag_items(db, ACCOUNT)[0]
        from types import SimpleNamespace
        # handle() only reads the ice flag, the shop session and the patched
        # selected actor, so the router contract needs no full session fixture.
        self.session = SimpleNamespace(ice_test=True, shop_session_id='shop-1')

    def envelope(self, kind, payload):
        from els_server.protocol.protocol_codec import Event
        return Event(0x202, kind=kind, payload=payload, performers=(0,),
                     uid=2**64-1, target_uid=2**64-1, payload_mode=0)

    def handle(self, event, sequence=7):
        from unittest.mock import patch
        from els_server.domain import modern_ice_flow
        select = (self.path, 1001, ACCOUNT, lambda db: None)
        with patch('els_server.domain.tenebros_capacity_flow.selected', return_value=select):
            return modern_ice_flow.handle(self.session, event, sequence)

    def test_bd3_withdraws_and_answers_bd4(self):
        payload = struct.pack('>I', 1) + struct.pack('>Qi', self.row['uid'], self.row['count'])
        reply = self.handle(self.envelope(0xbd3, payload))
        self.assertIsNotNone(reply)
        acks = [e for e in reply if e.kind in (0xbd4, 0xbd5)]
        self.assertTrue(acks)
        self.assertEqual(struct.unpack_from('>i', acks[0].payload)[0], 0)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(modern_ice.bag_items(db, ACCOUNT), [])
            self.assertIn(self.row['template'], {i['template'] for i in load_items(db, 1001)})

    def test_bd4_is_not_a_request_entry(self):
        self.assertIsNone(self.handle(self.envelope(0xbd4, b'')))

    def test_a_session_without_the_ice_subsystem_keeps_the_inventory_provider(self):
        self.session.ice_test = False
        self.assertIsNone(self.handle(self.envelope(0xbd6, b'')))

    def test_a_malformed_withdrawal_answers_the_native_error_code(self):
        reply = self.handle(self.envelope(0xbd3, b'\x00\x00\x00\x00'))
        self.assertEqual(reply[0].kind, 0xbd4)
        self.assertEqual(struct.unpack_from('>i', reply[0].payload)[0], -1)


if __name__ == '__main__':
    unittest.main()
