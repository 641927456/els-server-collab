"""Ordinary promotion fashion belongs in bag 7; only real ice fashion is bag 27.

Three box readers had classified native group7 fashion as group27, so a career
costume box delivered into the ice-fashion bag. fashion_inventory.native_groups
decides from the native flags8 bit 0x100 instead, and the character
initialization moves already-misfiled instances without touching their UID,
instance sub-tables or committed receipts.
"""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.fashion_inventory import native_groups
from els_server.domain.inventory_items import (FASHION_EQUIP_SLOTS, TEMPLATE_BAG_GROUPS,
                                              VERIFIED_TEMPLATES)
from els_server.domain import job_reward_boxes, owned_reward_boxes, promotion_reward_boxes
from els_server.domain.local_session import LocalAccount
from els_server.game_data import client_data
from els_server.storage.inventory_state import (InventoryState, grant_items, load_items)
from els_server.storage.local_state import LocalState

ORDINARY = 42573   # 不朽之王晋级大剑, ordinary group7 fashion
ICE = 131395       # a real ice-fashion piece, group27


class NativeGroupTests(unittest.TestCase):
    def test_the_native_flags8_bit_decides_the_bag(self):
        self.assertTrue(client_data().item(ORDINARY)['flags4'] & 1)
        self.assertFalse(client_data().item(ORDINARY)['flags8'] & 256)
        rows = native_groups([dict(template=ORDINARY, group=27), dict(template=ICE, group=7)])
        self.assertEqual([r['group'] for r in rows], [7, 27])

    def test_a_row_outside_the_fashion_groups_is_untouched(self):
        rows = native_groups([dict(template=ORDINARY, group=4), dict(template=ICE, group=9)])
        self.assertEqual([r['group'] for r in rows], [4, 9])

    def test_every_box_reader_agrees_with_the_registered_bag(self):
        client = client_data()
        for module in (owned_reward_boxes, job_reward_boxes, promotion_reward_boxes):
            for row in module.catalog()['readers']:
                if row['group'] not in (7, 27):
                    continue
                expected = 27 if client.item(row['template'])['flags8'] & 256 else 7
                self.assertEqual(row['group'], expected, row['template'])
                self.assertEqual(TEMPLATE_BAG_GROUPS[row['template']], expected)
                self.assertIn(row['template'], FASHION_EQUIP_SLOTS)


class NormalFashionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'save.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()

    def grant(self, template, count=1):
        """Ordinary career fashion is only obtainable from an owned box, so the
        acquisition policy refuses a bare grant. This case is about the bag
        migration, not the acquisition policy, so the policy is bypassed here."""
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            with patch('els_server.domain.acquisition_policy.require_acquirable',
                       lambda *a, **k: None):
                return grant_items(db, [dict(template=template,
                    metadata=VERIFIED_TEMPLATES[template],
                    group=TEMPLATE_BAG_GROUPS[template], quantity=count)])[0]

    def misplace(self, uid, slot=0):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE inventory_items SET bag_group=27,slot=? WHERE uid=? AND owner=1001', (slot, uid))

    def row(self, uid):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT uid,template,bag_group,slot FROM inventory_items WHERE uid=?', (uid,)).fetchone()

    def migration(self, name='ordinary-fashion-native-bag-7-v1:1001'):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT audit_json FROM inventory_migrations WHERE name=?', (name,)).fetchone()

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def test_a_misfiled_piece_moves_back_and_keeps_its_uid(self):
        item = self.grant(ORDINARY)
        self.assertEqual(self.row(item['uid'])[2], 7)
        receipts_before = self.dump()
        self.misplace(item['uid'])
        self.assertEqual(self.row(item['uid'])[2], 27)
        InventoryState(self.path, 1001)
        moved = self.row(item['uid'])
        self.assertEqual((moved[0], moved[1], moved[2]), (item['uid'], ORDINARY, 7))
        audit = json.loads(self.migration()[0])
        self.assertEqual(audit['changes'], [dict(uid=item['uid'], template=ORDINARY,
                                                before=[27, 0], after=[7, moved[3]])])
        self.assertTrue(audit['receipts_preserved'])
        # Same UID, same instance: only the inventory bag/slot columns moved,
        # and the only new row is the migration's own audit.
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIn(item['uid'], {i['uid'] for i in load_items(db, 1001)})
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        changed = set(receipts_before) ^ set(self.dump())
        self.assertTrue(changed)
        self.assertTrue(all(line.startswith(('INSERT INTO "inventory_items"',
                                             'INSERT INTO "inventory_migrations"'))
                            for line in changed), changed)

    def test_a_real_ice_piece_stays_in_bag_27(self):
        item = self.grant(ICE)
        self.assertEqual(self.row(item['uid'])[2], 27)
        InventoryState(self.path, 1001)
        self.assertEqual(self.row(item['uid'])[2], 27)
        self.assertIsNone(self.migration())

    def test_the_migration_runs_once(self):
        item = self.grant(ORDINARY)
        self.misplace(item['uid'])
        InventoryState(self.path, 1001)
        first = self.migration()
        InventoryState(self.path, 1001)
        self.assertEqual(self.migration(), first)


if __name__ == '__main__':
    unittest.main()
