"""Owned potions work through shortcuts, use, cooldown and reload.

Ordinary medicines were removed from the cash storefront by owner request;
the fixture grants existing inventory without changing that listing policy.
"""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from els_server.domain.consumables import ordinary, require_usable
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain.quick_bindings import item_binding
from els_server.protocol.protocol_codec import Event
from els_server.storage.consumables import use
from els_server.storage.local_state import LocalState
from els_server.storage.quick_slots import empty, encode, save_request
from els_server.storage.inventory_state import grant_items


def request(slot):
    return struct.pack('>HBBB', slot, 0, 0, 0)


class AdditionalPotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'potions.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.other = self.account.characters.create('OtherPotion', 5, 'other')['uid']
        self.account.for_character(self.other)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=500 WHERE uid=1001')
            grant_items(db, [dict(template=t, metadata=2, group=6, quantity=2)
                             for t in (77420, 77430, 78930)])
        self.bindings = {**empty(), **{slot: item_binding(t) for slot, t in enumerate((77420, 77430, 78930))}}
        save_request(self.path, struct.pack('>i', 1) + encode(self.bindings))

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def count(self, template, owner=1001):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT coalesce(sum(count),0) FROM inventory_items WHERE owner=? AND template=?', (owner, template)).fetchone()[0]

    def level(self, value):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE characters SET level=? WHERE uid=1001', (value,))

    def test_both_recovery_effects_emit_once_and_share_cooldown(self):
        balances = self.account.get_reward_balances()
        for template, hp in ((77420, 15), (77430, 30)):
            meta = ordinary(template)
            self.assertEqual([struct.unpack('<6I', bytes.fromhex(e)) for e in meta['effects']],
                             [(13, 0, hp, 0, 0, 0), (2, 0, 100, 0, 0, 0)])
        result = use(self.path, 1001, request(0), 'lower', now=100)
        self.assertEqual([e.kind for e in result], [0x114, 0x115])
        self.assertEqual(result[1].payload, struct.pack('>Qi?Q?', 1001, 77420, False, 0, False))
        self.assertEqual(self.count(77420), 1)
        before = self.dump()
        with self.assertRaisesRegex(ValueError, 'cooling down'):
            use(self.path, 1001, request(1), 'middle-early', now=129.99)
        self.assertEqual(self.dump(), before)
        self.assertEqual([e.kind for e in use(self.path, 1001, request(1), 'middle', now=130)], [0x114, 0x115])
        self.assertEqual(self.count(77430), 1)
        committed = self.dump()
        self.assertEqual([e.kind for e in use(self.path, 1001, request(0), 'lower', now=140)], [0x114])
        self.assertEqual(self.dump(), committed)
        restored = LocalAccount(LocalState(self.path))
        restored.enable_characters()
        self.assertEqual(restored.get_inventory_snapshot(), self.account.get_inventory_snapshot())
        self.assertEqual(restored.get_reward_balances(), balances)
        self.assertEqual(self.count(77420, self.other), 0)

    def test_mana_level_boundary_and_shared_native_cooldown(self):
        for level in (1, 59):
            self.level(level)
            before = self.dump()
            with self.assertRaisesRegex(ValueError, 'level requirement'):
                use(self.path, 1001, request(2), 'underlevel', now=100)
            self.assertEqual(self.dump(), before)
        self.level(60)
        result = use(self.path, 1001, request(2), 'allowed', now=100)
        self.assertEqual([e.kind for e in result], [0x114, 0x115])
        self.assertEqual(struct.unpack_from('>i', result[1].payload, 8)[0], 78930)
        self.assertEqual(self.count(78930), 1)
        with closing(sqlite3.connect(self.path)) as db, db:
            grant_items(db, [dict(template=77010, metadata=2, group=6, quantity=1)])
        save_request(self.path, struct.pack('>i', 1) + encode({**self.bindings, 3: item_binding(77010)}))
        with self.assertRaisesRegex(ValueError, 'cooling down'):
            use(self.path, 1001, request(3), 'basic-early', now=129.99)
        use(self.path, 1001, request(3), 'basic-ready', now=130)
        self.level(99)
        with self.assertRaisesRegex(ValueError, 'cooling down'):
            use(self.path, 1001, request(2), 'top-early', now=159.99)
        use(self.path, 1001, request(2), 'top-ready', now=160)
        self.assertEqual(self.count(78930), 0)
        self.assertEqual(require_usable(78930, 60)['cooldown_group'], 4)

    def test_encoder_failure_rolls_back_consumption_and_cooldown(self):
        before = self.dump()
        with patch('els_server.storage.consumables.effect', side_effect=RuntimeError('effect encoding failed')):
            with self.assertRaises(RuntimeError):
                use(self.path, 1001, request(0), 'retryable', now=100)
        self.assertEqual(self.dump(), before)
        use(self.path, 1001, request(0), 'retryable', now=100)
        self.assertEqual(self.count(77420), 1)

    def test_real_dispatch_rejects_low_level_then_accepts_same_request(self):
        session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
                               client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                               population_test=True, clear_test=True, reward_test=True, item_test=True)
        session.role = 'game'
        session.phase = 'dungeon_active'
        event = Event(0x202, kind=0x113, payload=request(2))
        before = self.dump()
        with patch('els_server.storage.consumables.time.time', return_value=100):
            self.assertEqual(session.handle(event, 100)[0].payload[:4], struct.pack('>i', -1))
            self.assertEqual(self.dump(), before)
            self.level(60)
            self.assertEqual([e.kind for e in session.handle(event, 100)], [0x114, 0x115])
            self.assertEqual([e.kind for e in session.handle(event, 100)], [0x114])
        self.assertEqual(self.count(78930), 1)


if __name__ == '__main__':
    unittest.main()
