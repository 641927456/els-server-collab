"""Actual 104 route: relocate/swap/merge, timed stacks, shortcuts and recovery."""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain.quick_bindings import item_binding
from els_server.protocol.protocol_codec import Event
from els_server.storage.bag_capacity import expand
from els_server.storage.consumables import use
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.item_expiration import assign
from els_server.storage.local_state import LocalState
from els_server.storage.potion_moves import move_potions
from els_server.storage.quick_slots import empty, encode, load, save_request


def request(source, destination, sg=6, dg=6, flag=0):
    return struct.pack('>BiBiB', sg, source, dg, destination, flag)


class PotionMoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'move.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.other = self.account.characters.create('OtherMover', 5, 'other')['uid']
        self.account.for_character(self.other)
        self.session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
                                    client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                                    population_test=True, clear_test=True, reward_test=True, item_test=True)
        self.session.role = 'game'
        self.session.phase = 'town_ready'

    def grant(self, template=77420, count=5, owner=1001, deadline=None):
        plan = dict(template=template, metadata=2, group=6, quantity=count)
        if deadline is not None:
            plan['expires_at'] = deadline
        with closing(sqlite3.connect(self.path)) as db, db:
            return grant_items(db, [plan], owner)[0]

    def items(self, owner=1001):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db, owner)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def dispatch(self, source, destination):
        reply = self.session.handle(Event(0x202, kind=0x104, payload=request(source, destination)))
        self.assertEqual([e.kind for e in reply], [0x105])
        self.assertEqual(reply[0].payload[-4:], bytes(4))
        return reply[0].payload

    def test_move_and_swap_preserve_uids_counts_balances_and_reload(self):
        first = self.grant()
        second = self.grant(77430, 7)
        balance = self.account.get_reward_balances()
        ack = self.dispatch(first['slot'], 5)
        self.assertEqual(len(ack), 656)
        self.assertEqual(struct.unpack_from('>I', ack)[0], 2)
        self.assertEqual(struct.unpack_from('>QBh', ack, 4), (0, 6, first['slot']))
        self.assertEqual(struct.unpack_from('>QBh', ack, 328), (first['uid'], 6, 5))
        moved = {i['uid']: i for i in self.items()}
        self.assertEqual(moved[first['uid']], dict(first, slot=5))
        self.dispatch(5, second['slot'])
        swapped = {i['uid']: i for i in self.items()}
        self.assertEqual(swapped[first['uid']], dict(first, slot=second['slot']))
        self.assertEqual(swapped[second['uid']], dict(second, slot=5))
        self.dispatch(5, second['slot'])  # A fresh identical swap must act again.
        self.assertEqual({i['uid']: i for i in self.items()}, moved)
        restored = LocalAccount(LocalState(self.path))
        self.assertEqual(restored.get_inventory_snapshot(), self.account.get_inventory_snapshot())
        self.assertEqual(self.account.get_reward_balances(), balance)

    def test_partial_merge_clamps_at_stack_limit_then_full_target_is_noop(self):
        first = self.grant(count=99)
        second = self.grant(count=10)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE inventory_items SET count=50 WHERE uid=?', (first['uid'],))
            db.execute('UPDATE inventory_items SET count=80 WHERE uid=?', (second['uid'],))
        self.dispatch(first['slot'], second['slot'])
        items = {i['uid']: i for i in self.items()}
        self.assertEqual((items[first['uid']]['count'], items[second['uid']]['count']), (31, 99))
        before = self.dump()
        self.dispatch(first['slot'], second['slot'])
        self.assertEqual(self.dump(), before)

    def test_complete_merge_removes_only_exhausted_uid_and_its_deadline(self):
        deadline = 2_100_000_000
        first = self.grant(count=99, deadline=deadline)
        second = self.grant(count=10, deadline=deadline)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE inventory_items SET count=3 WHERE uid=?', (first['uid'],))
            db.execute('UPDATE inventory_items SET count=5 WHERE uid=?', (second['uid'],))
        self.dispatch(first['slot'], second['slot'])
        items = {i['uid']: i for i in self.items()}
        self.assertNotIn(first['uid'], items)
        self.assertEqual(items[second['uid']], dict(second, count=8))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIsNone(db.execute('SELECT 1 FROM item_expiration WHERE item_uid=?', (first['uid'],)).fetchone())
            self.assertEqual(db.execute('SELECT expires_at FROM item_expiration WHERE item_uid=?', (second['uid'],)).fetchone(), (deadline,))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('PRAGMA quick_check').fetchall(), [('ok',)])
        before = self.dump()
        response = self.session.handle(Event(0x202, kind=0x104, payload=request(first['slot'], second['slot'])))
        self.assertEqual(response[0].payload[-4:], struct.pack('>i', -1))
        self.assertEqual(self.dump(), before)

    def test_different_deadlines_swap_without_merging_or_extending(self):
        first = self.grant(count=3, deadline=2_100_000_000)
        second = self.grant(count=5, deadline=2_100_000_100)
        self.dispatch(first['slot'], second['slot'])
        actual = {i['uid']: i for i in self.items()}
        self.assertEqual(actual[first['uid']], dict(first, slot=second['slot']))
        self.assertEqual(actual[second['uid']], dict(second, slot=first['slot']))

    def test_expanded_positions_and_character_capacity_are_respected(self):
        first = self.grant()
        self.grant(owner=self.other)
        other_before = self.items(self.other)
        with self.assertRaises(ValueError):
            move_potions(self.path, request(first['slot'], 36))
        with closing(sqlite3.connect(self.path)) as db, db:
            expand(db, 1001, 200753, 1)
        self.dispatch(first['slot'], 43)
        self.assertEqual(next(i for i in self.items() if i['uid'] == first['uid'])['slot'], 43)
        for destination in (44, 392, -1):
            before = self.dump()
            with self.assertRaises(ValueError):
                move_potions(self.path, request(43, destination))
            self.assertEqual(self.dump(), before)
        with self.assertRaises(ValueError):
            move_potions(self.path, request(0, 43), self.other)
        self.assertEqual(self.items(self.other), other_before)

    def test_shortcut_follows_template_after_move_and_consumes_new_position(self):
        first = self.grant()
        bindings = {**empty(), 5: item_binding(first['template'])}
        save_request(self.path, struct.pack('>i', 1) + encode(bindings))
        self.dispatch(first['slot'], 7)
        self.assertEqual(load(self.path), bindings)
        reply = use(self.path, 1001, struct.pack('>HBBB', 5, 0, 0, 0), 'after-move')
        self.assertEqual([e.kind for e in reply], [0x114, 0x115])
        self.assertEqual(struct.unpack_from('>QBh', reply[0].payload, 4), (first['uid'], 6, 7))
        self.assertEqual(next(i for i in self.items() if i['uid'] == first['uid'])['count'], 4)

    def test_encoder_and_audit_failures_leave_full_database_unchanged(self):
        first = self.grant(deadline=2_100_000_000)
        before = self.dump()
        with patch('els_server.storage.bag_moves.move_ack', side_effect=RuntimeError('encoding failure')):
            with self.assertRaises(RuntimeError):
                move_potions(self.path, request(first['slot'], 5))
        self.assertEqual(self.dump(), before)
        self.dispatch(first['slot'], 5)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TRIGGER refuse_move BEFORE INSERT ON bag_moves BEGIN SELECT RAISE(ABORT,'injected'); END")
        before = self.dump()
        with self.assertRaises(sqlite3.IntegrityError):
            move_potions(self.path, request(5, 6))
        self.assertEqual(self.dump(), before)

    def test_expired_items_invalid_requests_and_wrong_phases_do_not_move(self):
        first = self.grant()
        invalid = [b'', request(0, 1)[:-1], request(0, 1) + b'\0', request(0, 0),
                   request(0, 1, flag=1), request(0, 1, dg=9), request(-1, 1), request(0, 392)]
        before = self.dump()
        for packet in invalid:
            with self.assertRaises(ValueError):
                move_potions(self.path, packet)
            self.assertEqual(self.dump(), before)
        for phase in ('new', 'characters_ready', 'dungeon_active'):
            self.session.phase = phase
            reply = self.session.handle(Event(0x202, kind=0x104, payload=request(0, 5)))
            self.assertEqual(reply[0].payload[-4:], struct.pack('>i', -1))
            self.assertEqual(self.dump(), before)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            assign(db, 1001, first['uid'], 1_800_000_000)
        before = self.dump()
        with patch('els_server.domain.item_expiration.time.time', return_value=1_800_000_001):
            with self.assertRaisesRegex(ValueError, 'expired'):
                move_potions(self.path, request(0, 5))
        self.assertEqual(self.dump(), before)


if __name__ == '__main__':
    unittest.main()
