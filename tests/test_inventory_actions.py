"""Split/discard buttons: counts, UID ownership, replay, reload and rollback."""
import sqlite3
import struct
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.protocol.inventory_action_messages import discard_ack
from els_server.protocol.protocol_codec import Event
from els_server.storage.bag_capacity import expand
from els_server.storage.inventory_actions import split_stack, discard
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.local_state import LocalState


def split_wire(source, destination, count, group=6):
    return struct.pack('>BiBii', group, source, group, destination, count)


def discard_wire(uid, count):
    return struct.pack('>Qi', uid, count)


class InventoryActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'actions.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.other = self.account.characters.create('ActionOther', 5, 'other')['uid']
        self.account.for_character(self.other)
        self.first = self.grant()
        self.session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
                                    client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                                    population_test=True, clear_test=True, reward_test=True, item_test=True)
        self.session.role = 'game'
        self.session.phase = 'town_ready'

    def grant(self, template=77420, count=10, owner=1001, deadline=None):
        plan = dict(template=template, metadata=VERIFIED_TEMPLATES[template],
                    group=TEMPLATE_BAG_GROUPS[template], quantity=count)
        if deadline is not None:
            plan['expires_at'] = deadline
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            return grant_items(db, [plan], owner)[0]

    def items(self, owner=1001):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db, owner)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def test_split_dispatch_and_reload_preserve_total_and_economy(self):
        balance = self.account.get_reward_balances()
        event = Event(0x202, kind=0x555, payload=split_wire(self.first['slot'], 5, 3))
        result = self.session.handle(event, 100)
        self.assertEqual([e.kind for e in result], [0x556])
        self.assertEqual(len(result[0].payload), 660)
        self.assertEqual(result[0].payload[-8:], bytes(8))
        potions = [i for i in self.items() if i['template'] == self.first['template']]
        self.assertEqual(sorted((i['slot'], i['count']) for i in potions), [(self.first['slot'], 7), (5, 3)])
        self.assertEqual(len({i['uid'] for i in potions}), 2)
        self.assertEqual(next(i for i in potions if i['slot'] == self.first['slot'])['uid'], self.first['uid'])
        before = self.dump()
        self.assertEqual(self.session.handle(event, 100), result)
        self.assertEqual(self.dump(), before)
        restored = LocalAccount(LocalState(self.path))
        self.assertEqual(restored.get_inventory_snapshot(), self.account.get_inventory_snapshot())
        self.assertEqual(self.account.get_reward_balances(), balance)

    def test_full_count_split_moves_existing_uid_without_sequence_increment(self):
        with closing(sqlite3.connect(self.path)) as db:
            sequence = db.execute('SELECT next_uid FROM inventory_sequence').fetchone()
        split_stack(self.path, 1001, split_wire(self.first['slot'], 7, 10), 'all')
        self.assertIn(dict(self.first, slot=7), self.items())
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT next_uid FROM inventory_sequence').fetchone(), sequence)

    def test_timed_split_keeps_original_absolute_deadline(self):
        item = self.grant(77430, 8, deadline=2_100_000_000)
        split_stack(self.path, 1001, split_wire(item['slot'], 9, 3), 'timed')
        parts = [i for i in self.items() if i['template'] == 77430]
        self.assertEqual(sorted(i['count'] for i in parts), [3, 5])
        self.assertTrue(all(i['expires_at'] == item['expires_at'] for i in parts))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_split_empty_destination_capacity_invalid_counts_and_owner(self):
        self.grant(77430, 5)
        for wire in (split_wire(0, 1, 3), split_wire(0, 36, 3), split_wire(0, 2, 11),
                     split_wire(0, 0, 3), split_wire(0, 2, 0), split_wire(0, 2, -1), b'bad'):
            before = self.dump()
            with self.assertRaises(ValueError):
                split_stack(self.path, 1001, wire, 'invalid')
            self.assertEqual(self.dump(), before)
        with self.assertRaises(ValueError):
            split_stack(self.path, self.other, split_wire(0, 2, 3), 'foreign')
        with closing(sqlite3.connect(self.path)) as db, db:
            expand(db, 1001, 200753, 1)
        split_stack(self.path, 1001, split_wire(0, 43, 3), 'expanded')
        self.assertTrue(any(i['slot'] == 43 and i['group'] == 6 for i in self.items()))

    def test_discard_partial_full_and_retry_after_slot_replacement(self):
        before_balance = self.account.get_reward_balances()
        wire = discard_wire(self.first['uid'], 3)
        reply = self.session.handle(Event(0x202, kind=0x109, payload=wire), 101)
        self.assertEqual([e.kind for e in reply], [0x10a])
        self.assertEqual(reply[0].payload[:12], bytes(12))
        self.assertEqual(next(i for i in self.items() if i['uid'] == self.first['uid'])['count'], 7)
        discard(self.path, 1001, discard_wire(self.first['uid'], 7), 'remove')
        replacement = self.grant(77430, 2)
        self.assertEqual(replacement['slot'], self.first['slot'])
        committed = self.dump()
        retried = self.session.handle(Event(0x202, kind=0x109, payload=wire), 101)
        self.assertEqual(retried[0].payload, discard_ack(replacement, (6, replacement['slot'])))
        self.assertEqual(self.dump(), committed)
        with self.assertRaises(ValueError):
            discard(self.path, 1001, wire, 'new-request-for-removed-uid')
        self.assertEqual(self.account.get_reward_balances(), before_balance)

    def test_discard_rejects_foreign_uid_and_oversized_count(self):
        foreign = self.grant(owner=self.other)
        for wire in (discard_wire(foreign['uid'], 1), discard_wire(self.first['uid'], 11),
                     discard_wire(self.first['uid'], 0), discard_wire(self.first['uid'], -1),
                     discard_wire(2**63, 1), b'bad'):
            before = self.dump()
            with self.assertRaises(ValueError):
                discard(self.path, 1001, wire, 'invalid')
            self.assertEqual(self.dump(), before)

    def test_full_equipment_discard_cleans_uid_owned_auxiliary_tables(self):
        item = self.grant(60100, 1, deadline=2_100_000_000)
        from els_server.storage.equipment_enhancement import replace
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            replace(db, 1001, item['uid'], 0, 3)
        discard(self.path, 1001, discard_wire(item['uid'], 1), 'equipment')
        self.assertFalse(any(i['uid'] == item['uid'] for i in self.items()))
        with closing(sqlite3.connect(self.path)) as db:
            for table in ('equipment_durability', 'equipment_enhancement', 'item_expiration'):
                self.assertIsNone(db.execute(f'SELECT 1 FROM {table} WHERE item_uid=?', (item['uid'],)).fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_equipped_items_and_expired_stacks_are_not_discarded_or_split(self):
        item = self.grant(60100, 1)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE inventory_items SET bag_group=9,slot=9 WHERE uid=?', (item['uid'],))
        before = self.dump()
        with self.assertRaisesRegex(ValueError, 'owned bag item'):
            discard(self.path, 1001, discard_wire(item['uid'], 1), 'worn')
        self.assertEqual(self.dump(), before)
        timed = self.grant(77430, 5, deadline=2_100_000_000)
        before = self.dump()
        with patch('els_server.domain.item_expiration.time.time', return_value=2_100_000_001):
            with self.assertRaisesRegex(ValueError, 'expired'):
                split_stack(self.path, 1001, split_wire(timed['slot'], 7, 2), 'expired-split')
            with self.assertRaisesRegex(ValueError, 'expired'):
                discard(self.path, 1001, discard_wire(timed['uid'], 1), 'expired-discard')
        self.assertEqual(self.dump(), before)

    def test_split_retry_restores_current_counts_after_later_discard(self):
        wire = split_wire(0, 5, 3)
        split_stack(self.path, 1001, wire, 'original')
        discard(self.path, 1001, discard_wire(self.first['uid'], 2), 'later')
        before = self.dump()
        response = split_stack(self.path, 1001, wire, 'original')
        from els_server.protocol.inventory_action_messages import split_ack
        items = {i['slot']: i for i in self.items() if i['group'] == 6}
        self.assertEqual(response, split_ack([((6, 0), items[0]), ((6, 5), items[5])]))
        self.assertEqual(items[0]['count'], 5)
        self.assertEqual(self.dump(), before)

    def test_failure_rolls_back_count_uid_sequence_and_receipt(self):
        before = self.dump()
        with patch('els_server.storage.inventory_actions.split_ack', side_effect=RuntimeError('encode')):
            with self.assertRaises(RuntimeError):
                split_stack(self.path, 1001, split_wire(0, 5, 3), 'encode-failure')
        self.assertEqual(self.dump(), before)
        split_stack(self.path, 1001, split_wire(0, 5, 3), 'initialize')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TRIGGER fail_action BEFORE INSERT ON inventory_action_receipts BEGIN SELECT RAISE(ABORT,'injected'); END")
        before = self.dump()
        with self.assertRaises(sqlite3.IntegrityError):
            split_stack(self.path, 1001, split_wire(0, 6, 2), 'sql-failure')
        self.assertEqual(self.dump(), before)
        with self.assertRaises(sqlite3.IntegrityError):
            discard(self.path, 1001, discard_wire(self.first['uid'], 7), 'discard-failure')
        self.assertEqual(self.dump(), before)

    def test_concurrent_retry_allocates_and_decrements_once_and_conflicts_fail(self):
        wire = split_wire(0, 5, 3)
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: split_stack(self.path, 1001, wire, 'same'), range(4)))
        self.assertEqual(len(set(replies)), 1)
        parts = [i for i in self.items() if i['template'] == self.first['template']]
        self.assertEqual(len(parts), 2)
        self.assertEqual(sum(i['count'] for i in parts), 10)
        before = self.dump()
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            split_stack(self.path, 1001, split_wire(0, 6, 2), 'same')
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            discard(self.path, 1001, discard_wire(self.first['uid'], 1), 'same')
        self.assertEqual(self.dump(), before)

    def test_phase_and_sequence_rejections_send_failure_without_mutation(self):
        before = self.dump()
        for phase, sequence in (('new', 1), ('dungeon_active', 2), ('town_ready', None), ('town_ready', 0)):
            self.session.phase = phase
            split = self.session.handle(Event(0x202, kind=0x555, payload=split_wire(0, 5, 3)), sequence)
            discard_reply = self.session.handle(Event(0x202, kind=0x109, payload=discard_wire(self.first['uid'], 1)), sequence)
            self.assertEqual(split[0].payload[-4:], struct.pack('>i', -1))
            self.assertEqual(discard_reply[0].payload[:4], struct.pack('>i', -1))
        self.assertEqual(self.dump(), before)


if __name__ == '__main__':
    unittest.main()
