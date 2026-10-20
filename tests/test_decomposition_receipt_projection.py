"""Portable SQLite projection tests; no reward definitions or runtime assets.

The production caller already verifies the request digest with _previous.
These fixtures exercise the existing receipt owner's current UID projection;
they do not simulate reward selection, item grants, or network frame replay.
"""
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from els_server.storage.equipment_receipt_state import current_changes


class DecompositionReceiptProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'projection.sqlite3'
        # Minimal fixture projections only. No template, probability or reward
        # definition is created; these are not production schema migrations.
        self.source = dict(uid=100001, group=1, slot=0, count=1)
        self.retained = dict(uid=100002, group=3, slot=0, count=10)
        self.positions = [(1, 0), (3, 0)]
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('''CREATE TABLE inventory_action_receipts (
                operation_id TEXT PRIMARY KEY, owner INTEGER, kind INTEGER,
                before_json TEXT, after_json TEXT)''')
            db.execute('''INSERT INTO inventory_action_receipts VALUES (?,?,?,?,?)''',
                       ('receipt', 1001, 0x1c0,
                        json.dumps([self.source, self.retained]),
                        json.dumps([self.retained])))
            db.execute('''CREATE TABLE current_rows (
                uid INTEGER PRIMARY KEY,owner INTEGER,bag_group INTEGER,
                slot INTEGER,count INTEGER)''')

    def insert(self, item, owner=1001):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO current_rows VALUES (?,?,?,?,?)',
                       (item['uid'], owner, item['group'], item['slot'], item['count']))

    def snapshot(self, db, owner):
        return [dict(zip(('uid', 'group', 'slot', 'count'), row)) for row in db.execute(
            'SELECT uid,bag_group,slot,count FROM current_rows WHERE owner=? ORDER BY bag_group,slot',
            (owner,))]

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def project(self, *, operation='receipt', owner=1001, kind=0x1c0):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN')
            return current_changes(db, operation, owner, kind, self.positions,
                                   self.snapshot(db, owner))

    def test_moved_uid_uses_current_count_and_preserves_old_slot_replacements(self):
        moved = dict(self.retained, slot=7, count=4)
        replacement = dict(uid=100003, group=3, slot=0, count=2)
        source_replacement = dict(uid=100004, group=1, slot=0, count=1)
        self.insert(moved)
        self.insert(replacement)
        self.insert(source_replacement)
        before = self.dump()
        self.assertEqual(self.project(), [((1, 0), source_replacement),
                                         ((3, 0), replacement), ((3, 7), moved)])
        self.assertEqual(self.dump(), before)
        # Each call opens fresh read connections; no historical source object
        # or output template lookup is needed after the old instance is gone.
        self.assertEqual(self.project()[-1], ((3, 7), moved))

    def test_uid_transferred_to_another_role_is_not_projected_back(self):
        foreign = dict(self.retained, slot=6)
        self.insert(foreign, owner=1002)
        before = self.dump()
        self.assertEqual(self.project(), [((1, 0), None), ((3, 0), None)])
        self.assertEqual(self.dump(), before)

    def test_consumed_uid_does_not_select_unrelated_current_row(self):
        unrelated = dict(uid=100099, group=3, slot=9, count=4)
        self.insert(unrelated)
        before = self.dump()
        self.assertEqual(self.project(), [((1, 0), None), ((3, 0), None)])
        self.assertEqual(self.dump(), before)

    def test_same_affected_position_is_returned_once_in_historical_order(self):
        self.insert(self.retained)
        self.assertEqual(self.project(), [((1, 0), None), ((3, 0), self.retained)])

    def test_missing_owner_or_kind_conflicts_are_rejected_without_changes(self):
        before = self.dump()
        for values in (dict(operation='missing'), dict(owner=1002), dict(kind=0x196)):
            with self.subTest(values=values), self.assertRaisesRegex(
                    ValueError, 'Equipment receipt owner or kind mismatch'):
                self.project(**values)
            self.assertEqual(self.dump(), before)
        with self.assertRaisesRegex(ValueError, 'Unreviewed equipment receipt kind'):
            self.project(kind=0x7fffffff)
        self.assertEqual(self.dump(), before)

    def test_malformed_history_fails_readonly(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE inventory_action_receipts SET before_json=?', ('[null]',))
        before = self.dump()
        with self.assertRaisesRegex(ValueError, 'Equipment receipt item arrays'):
            self.project()
        self.assertEqual(self.dump(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
