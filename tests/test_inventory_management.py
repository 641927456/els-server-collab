"""Inventory UI ownership, fees, retries, attachments and atomic rollback."""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.inventory_management import sort_inventory, lock_item
from els_server.storage.inventory_actions import split_stack, discard
from els_server.storage.equipment_enhancement import replace


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'save.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.account.for_character(self.account.characters.create('LockOther', 5, 'other')['uid'])
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=1000000 WHERE uid=1001')
        self.gear = self.grant(60100)

    def grant(self, template, count=1, deadline=None):
        p = dict(template=template, metadata=VERIFIED_TEMPLATES[template],
                 group=TEMPLATE_BAG_GROUPS[template], quantity=count)
        if deadline is not None:
            p['expires_at'] = deadline
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            return grant_items(db, [p])[0]

    def items(self):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def lock(self, days=2, uid=None, operation='lock', action=0):
        return lock_item(self.path, 1001, struct.pack('>QhiB', uid or self.gear['uid'], days, action, 0), operation)

    def test_lock_fee_deadline_reload_retry_and_discard_protection(self):
        with patch('els_server.storage.inventory_management.time.time', return_value=2000000000):
            events = self.lock()
        self.assertEqual([e.kind for e in events], [0x664, 0x105])
        self.assertEqual(struct.unpack('>iQi', events[0].payload), (0, 980000, 0))
        item = next(i for i in self.items() if i['uid'] == self.gear['uid'])
        self.assertEqual(item['lock_until'], 2000172800)
        self.assertEqual(LocalAccount(LocalState(self.path)).get_inventory_snapshot()['items'], self.items())
        before = self.dump()
        self.assertEqual(self.lock(), events)
        self.assertEqual(self.dump(), before)
        with self.assertRaises(ValueError):
            discard(self.path, 1001, struct.pack('>Qi', item['uid'], 1), 'discard-locked')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(ValueError):
                replace(db, 1001, item['uid'], 0, 1)
        self.assertEqual(self.dump(), before)

    def test_reject_cheat_bad_days_owner_funds_and_early_unlock(self):
        bad = [struct.pack('>QhiB', self.gear['uid'], n, 0, 0) for n in (-1, 0, 31)]
        bad += [struct.pack('>QhiB', self.gear['uid'], 1, 0, 1), b'',
                struct.pack('>QhiB', self.gear['uid']+100, 1, 0, 0)]
        for payload in bad:
            before = self.dump()
            with self.assertRaises(ValueError):
                lock_item(self.path, 1001, payload, 'bad')
            self.assertEqual(self.dump(), before)
        with self.assertRaises(ValueError):
            lock_item(self.path, 1002, struct.pack('>QhiB', self.gear['uid'], 1, 0, 0), 'foreign')
        self.lock()
        before = self.dump()
        with self.assertRaises(ValueError):
            self.lock(0, action=1, operation='early-unlock')
        self.assertEqual(self.dump(), before)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=0 WHERE uid=1001')
        another = self.grant(60110)
        before = self.dump()
        with self.assertRaises(ValueError):
            self.lock(uid=another['uid'], operation='poor')
        self.assertEqual(self.dump(), before)

    def test_expired_lock_can_be_cleared_and_discarded(self):
        with patch('els_server.storage.inventory_management.time.time', return_value=1000000000):
            self.lock()
        self.lock(0, action=1, operation='clear-expired')
        item = next(i for i in self.items() if i['uid'] == self.gear['uid'])
        self.assertNotIn('lock_until', item)
        discard(self.path, 1001, struct.pack('>Qi', item['uid'], 1), 'discard')
        self.assertNotIn(item['uid'], {i['uid'] for i in self.items()})

    def test_lock_rollback_on_encoder_failure_and_concurrent_retry(self):
        before = self.dump()
        with patch('els_server.storage.inventory_management.lock_ack', side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):
                self.lock()
        self.assertEqual(self.dump(), before)
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: self.lock(), range(2)))
        self.assertEqual(replies[0], replies[1])
        self.assertEqual(self.account.get_reward_balances()['ed'], 980000)

    def test_sort_merge_dates_replay_and_locked_equipment_preserve(self):
        self.lock()
        potion = self.grant(77420, 20)
        split_stack(self.path, 1001, struct.pack('>BiBii', 6, potion['slot'], 6, 20, 7), 'split')
        timed = self.grant(77420, 4, 2100000000)
        bait = self.grant(135983, 9)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE inventory_items SET slot=15 WHERE uid=?', (bait['uid'],))
        before = self.items()
        balance = self.account.get_reward_balances()
        result = sort_inventory(self.path, 1001, b'', 'sort')
        self.assertEqual(result[0].kind, 0xbd7)
        current = self.items()
        potions = [i for i in current if i['template'] == 77420]
        self.assertEqual(sorted(i['count'] for i in potions), [4, 20])
        self.assertEqual(next(i for i in potions if 'expires_at' in i)['uid'], timed['uid'])
        self.assertEqual(next(i for i in current if i['uid'] == self.gear['uid']), next(i for i in before if i['uid'] == self.gear['uid']))
        self.assertEqual(next(i for i in current if i['uid'] == bait['uid'])['slot'], 0)
        self.assertEqual(self.account.get_reward_balances(), balance)
        after = self.dump()
        self.assertEqual(sort_inventory(self.path, 1001, b'', 'sort'), result)
        self.assertEqual(self.dump(), after)

    def test_sort_keeps_enhancement_attributes_and_rolls_back_on_wire_error(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            replace(db, 1001, self.gear['uid'], 0, 3)
            db.execute('UPDATE inventory_items SET slot=19 WHERE uid=?', (self.gear['uid'],))
        before = self.dump()
        with patch('els_server.storage.inventory_management.sort_ack', side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):
                sort_inventory(self.path, 1001, b'', 'sort')
        self.assertEqual(self.dump(), before)
        sort_inventory(self.path, 1001, b'', 'sort')
        item = next(i for i in self.items() if i['uid'] == self.gear['uid'])
        self.assertEqual((item['slot'], item['enhancement']), (0, 3))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_phase_sequence_and_dispatch(self):
        session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
                               client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                               population_test=True, clear_test=True, reward_test=True, item_test=True)
        session.role, session.phase = 'game', 'town_ready'
        event = Event(0x202, kind=0xbd6)
        self.assertEqual(session.handle(event, 10)[0].kind, 0xbd7)
        for phase, sequence in (('dungeon_active', 11), ('town_ready', 0), ('town_ready', None)):
            session.phase = phase
            before = self.dump()
            result = session.handle(event, sequence)
            self.assertEqual(struct.unpack_from('>i', result[0].payload)[0], -1)
            self.assertEqual(self.dump(), before)

    def test_timed_locked_item_still_expires_without_dangling_lock(self):
        from els_server.storage.item_expiration import assign as set_expiration, remove_due
        self.lock()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            set_expiration(db, 1001, self.gear['uid'], 2000000000)
        remove_due(self.path, 1001, now=2000000001)
        self.assertNotIn(self.gear['uid'], {i['uid'] for i in self.items()})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertFalse(db.execute('SELECT 1 FROM item_locks WHERE item_uid=?', (self.gear['uid'],)).fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])


if __name__ == '__main__':
    unittest.main()
