import unittest, sqlite3, struct
from contextlib import closing
from unittest.mock import patch
from tests import test_npc_sale as fixture
from tests.test_bank_state import payload
from els_server.storage.bank_state import transfer, snapshot
from els_server.protocol.bank_messages import transfer_ack

class SaleLimitTests(unittest.TestCase):
    setUp = fixture.SaleTests.setUp
    grant = fixture.SaleTests.grant
    items = fixture.SaleTests.items
    dump = fixture.SaleTests.dump
    money = fixture.SaleTests.money

    def fund(self, ed, level=1):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=? WHERE uid=1001', (ed,))
            db.execute('UPDATE characters SET level=? WHERE uid=1001', (level,))

    def test_sale_above_current_native_level_limit_rolls_back(self):
        from els_server.storage.npc_sale import sell
        self.fund(500000 - 23520 + 1)
        before = self.dump()
        with self.assertRaises(ValueError):
            sell(self.path, 1001, fixture.payload([(self.gear['uid'], 1)]), 'over-wallet')
        self.assertEqual(self.dump(), before)

    def test_sale_at_exact_native_limit_commits_and_retry_survives_later_above_limit_balance(self):
        from els_server.storage.npc_sale import sell
        self.fund(500000 - 23520)
        wire = fixture.payload([(self.gear['uid'], 1)])
        sell(self.path, 1001, wire, 'at-wallet')
        self.assertEqual(self.money(), 500000)
        self.fund(500001)
        before = self.dump()
        events = sell(self.path, 1001, wire, 'at-wallet')
        self.assertEqual(self.dump(), before)
        self.assertEqual(struct.unpack_from('>iQ', events[0].payload), (0, 500001))

    def test_batch_total_limit_and_level99_authority(self):
        from els_server.storage.npc_sale import sell
        second = self.grant(30160)
        self.fund(499999)
        before = self.dump()
        with self.assertRaises(ValueError):
            sell(self.path, 1001, fixture.payload([(self.gear['uid'], 1), (second['uid'], 1)]), 'batch-wallet')
        self.assertEqual(self.dump(), before)
        self.fund(1000000000, 99)
        sell(self.path, 1001, fixture.payload([(self.gear['uid'], 1), (second['uid'], 1)]), 'valid-99')
        self.assertGreater(self.money(), 1000000000)

if __name__ == '__main__': unittest.main()
