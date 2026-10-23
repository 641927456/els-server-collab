import unittest, sqlite3, struct
from contextlib import closing
from unittest.mock import patch
from tests import test_npc_sale as fixture
from tests.test_bank_state import payload
from els_server.storage.bank_state import transfer, snapshot
from els_server.protocol.bank_messages import transfer_ack

class BankReceiptTests(unittest.TestCase):
    setUp = fixture.SaleTests.setUp
    grant = fixture.SaleTests.grant
    items = fixture.SaleTests.items
    dump = fixture.SaleTests.dump

    def test_retry_refreshes_moved_original_uid_but_preserves_historical_occupants(self):
        item = self.gear
        source = (item['group'], item['slot'])
        old = payload(source, (8, 0), item)
        transfer(self.path, 1001, old, 'first-deposit')
        transfer(self.path, 1001, payload((8, 0), (1, 35), item), 'withdraw-third')
        replacement = self.grant(30160)
        transfer(self.path, 1001, payload((replacement['group'], replacement['slot']), (8, 0), replacement), 'replace-bank')
        replacement_bag = self.grant(60100)
        before = self.dump()
        answer = transfer(self.path, 1001, old, 'first-deposit')
        current = {(i['group'], i['slot']): i for i in self.items()}
        current.update(((tuple(e['position']), e['item']) for e in snapshot(self.path, 1001)['bank_items']))
        self.assertEqual(self.dump(), before)
        self.assertEqual(answer, transfer_ack([(p, current.get(p)) for p in (source, (8, 0), (1, 35))]))

    def test_retry_does_not_restore_uid_withdrawn_by_sibling(self):
        item = self.gear
        source = (item['group'], item['slot'])
        old = payload(source, (16, 0), item)
        transfer(self.path, 1001, old, 'first-shared')
        transfer(self.path, self.other, payload((16, 0), (1, 35), item), 'sibling-withdraw')
        before = self.dump()
        answer = transfer(self.path, 1001, old, 'first-shared')
        current = {(i['group'], i['slot']): i for i in self.items()}
        self.assertEqual(answer, transfer_ack([(p, current.get(p)) for p in (source, (16, 0))]))
        self.assertEqual(self.dump(), before)

    def test_retry_refreshes_affected_uid_moved_between_bank_containers(self):
        item = self.gear
        source = (item['group'], item['slot'])
        old = payload(source, (8, 0), item)
        transfer(self.path, 1001, old, 'deposit-original')
        transfer(self.path, 1001, payload((8, 0), (16, 6), item), 'move-shared')
        before = self.dump()
        answer = transfer(self.path, 1001, old, 'deposit-original')
        self.assertEqual(answer, transfer_ack([(source, None), ((8, 0), None), ((16, 6), item)]))
        self.assertEqual(self.dump(), before)

    def test_replay_checks_receipt_owner_and_encode_failure_remains_atomic(self):
        item = self.gear
        source = (item['group'], item['slot'])
        old = payload(source, (8, 0), item)
        transfer(self.path, 1001, old, 'receipt-guard')
        before = self.dump()
        with patch('els_server.storage.bank_state.transfer_ack', side_effect=ValueError('encode')):
            with self.assertRaises(ValueError):
                transfer(self.path, 1001, old, 'receipt-guard')
        self.assertEqual(self.dump(), before)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE inventory_action_receipts SET owner=? WHERE operation_id=?', (self.other, 'receipt-guard'))
        before = self.dump()
        with self.assertRaises(ValueError):
            transfer(self.path, 1001, old, 'receipt-guard')
        self.assertEqual(self.dump(), before)

if __name__ == '__main__': unittest.main()
