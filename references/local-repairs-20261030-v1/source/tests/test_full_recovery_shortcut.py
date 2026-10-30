"""The full-recovery shortcut owns two templates; both must stay usable.

Bag binding412 is shared by the admitted130165 and the native710000 record.
Before this, the ambiguous-template guard refused the shortcut outright while
the catalog row itself was neither admitted nor timer-configurable.
"""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from els_server.domain.consumables import catalog, ordinary, require_usable
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain.quick_bindings import item_binding
from els_server.protocol.protocol_codec import Event
from els_server.storage.consumables import use
from els_server.storage.inventory_state import grant_items
from els_server.storage.local_state import LocalState
from els_server.storage.quick_slots import empty, encode, save_request


def request(slot):
    return struct.pack('>HBBB', slot, 0, 0, 0)


class FullRecoveryShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'full-recovery.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        with closing(sqlite3.connect(self.path)) as db, db:
            grant_items(db, [dict(template=130165, metadata=2, group=6, quantity=3)])
            grant_items(db, [dict(template=710000, metadata=2, group=6, quantity=4)])
        self.assertEqual(item_binding(130165), item_binding(710000))
        save_request(self.path, struct.pack('>i', 1) + encode({**empty(), 0: item_binding(130165)}))

    def count(self, template):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT coalesce(sum(count),0) FROM inventory_items WHERE owner=1001 AND template=?',
                              (template,)).fetchone()[0]

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def test_evidence_stays_client_exact_while_the_local_timer_is_one_second(self):
        row = catalog()[130165]
        meta = ordinary(130165)
        self.assertEqual((row['cooldown_group'], row['cooldown_seconds'], bytes.fromhex(row['record_hex'])[0xd6]),
                         (15, 30, 30))
        self.assertEqual((meta['cooldown_group'], meta['cooldown_seconds']), (15, 1))
        self.assertEqual(meta['effects'], row['effects'])
        self.assertEqual(require_usable(130165, 95)['cooldown_seconds'], 1)
        self.assertEqual(require_usable(710000, 95)['cooldown_seconds'], 30)

    def test_lowest_bag_slot_wins_and_one_second_reopens_the_shortcut(self):
        result = use(self.path, 1001, request(0), 'first', now=100)
        self.assertEqual([e.kind for e in result], [0x114, 0x115])
        # 0x114 tail is template,bool,cooldown,slot; the admitted row reports1s.
        self.assertEqual(struct.unpack_from('>f', result[0].payload, len(result[0].payload) - 6)[0], 1.0)
        self.assertEqual((self.count(130165), self.count(710000)), (2, 4))
        before = self.dump()
        with self.assertRaisesRegex(ValueError, 'cooling down'):
            use(self.path, 1001, request(0), 'early', now=100.99)
        self.assertEqual(self.dump(), before)
        self.assertEqual([e.kind for e in use(self.path, 1001, request(0), 'ready', now=101)], [0x114, 0x115])
        self.assertEqual((self.count(130165), self.count(710000)), (1, 4))
        committed = self.dump()
        self.assertEqual([e.kind for e in use(self.path, 1001, request(0), 'first', now=101)], [0x114])
        self.assertEqual(self.dump(), committed)

    def test_the_native_row_keeps_its_thirty_second_group(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM inventory_items WHERE owner=1001 AND template=130165')
        native = use(self.path, 1001, request(0), 'native', now=100)
        self.assertEqual([e.kind for e in native], [0x114, 0x115])
        self.assertEqual(struct.unpack_from('>f', native[0].payload, len(native[0].payload) - 6)[0], -1.0)
        self.assertEqual(self.count(710000), 3)
        with self.assertRaisesRegex(ValueError, 'cooling down'):
            use(self.path, 1001, request(0), 'native-early', now=129.99)
        self.assertEqual([e.kind for e in use(self.path, 1001, request(0), 'native-ready', now=130)], [0x114, 0x115])

    def test_dispatch_accepts_the_shortcut_request(self):
        session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
                               client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                               population_test=True, clear_test=True, reward_test=True, item_test=True)
        session.role = 'game'
        session.phase = 'dungeon_active'
        with patch('els_server.storage.consumables.time.time', return_value=200):
            answered = session.handle(Event(0x202, kind=0x113, payload=request(0)), 7)
        self.assertEqual([e.kind for e in answered], [0x114, 0x115])
        self.assertEqual(answered[0].payload[:4], struct.pack('>i', 0))
        self.assertEqual(self.count(130165), 2)


if __name__ == '__main__':
    unittest.main()
