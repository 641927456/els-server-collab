"""Original-rule dismantling: reward identity, ownership and loss prevention."""
import sqlite3
import struct
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.domain.decomposition_rules import quote
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.inventory_management import lock_item
from els_server.storage.decomposition import decompose
from els_server.storage.equipment_enhancement import replace


def request(*uids, special=0):
    return struct.pack('>I', len(uids)) + b''.join(struct.pack('>Q', u) for u in uids) + bytes([special])


class DecompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'decompose.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.account.for_character(self.account.characters.create('DecompOther', 5, 'other')['uid'])
        self.gear = self.grant(30160)

    def grant(self, template, quantity=1):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            return grant_items(db, [dict(template=template, metadata=VERIFIED_TEMPLATES[template],
                group=TEMPLATE_BAG_GROUPS[template], quantity=quantity)])[0]

    def items(self):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def crystals(self):
        return sum(i['count'] for i in self.items() if i['template'] == 701000)

    def test_exact_original_yield_batch_and_reload(self):
        self.assertEqual(quote(self.gear)['resale_ed'], 36000)
        second = self.grant(30230)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            replace(db, 1001, self.gear['uid'], 0, 3)
        balance = self.account.get_reward_balances()
        response = decompose(self.path, 1001, request(self.gear['uid'], second['uid']), 'batch')
        self.assertEqual(response[0].kind, 0x1c1)
        self.assertEqual(struct.unpack_from('>iBIii', response[0].payload), (0, 0, 1, 701000, 72))
        self.assertEqual(self.crystals(), 72)
        self.assertFalse({self.gear['uid'], second['uid']} & {i['uid'] for i in self.items()})
        self.assertEqual(self.account.get_reward_balances(), balance)
        self.assertEqual(LocalAccount(LocalState(self.path)).get_inventory_snapshot()['items'], self.items())
        with closing(sqlite3.connect(self.path)) as db:
            self.assertFalse(db.execute('SELECT 1 FROM equipment_enhancement WHERE item_uid=?', (self.gear['uid'],)).fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_repeat_reports_current_state_without_second_reward(self):
        wire = request(self.gear['uid'])
        decompose(self.path, 1001, wire, 'once')
        current = self.crystals()
        self.grant(701000, 5)
        before = self.dump()
        result = decompose(self.path, 1001, wire, 'once')
        self.assertEqual(self.crystals(), current+5)
        self.assertEqual(self.dump(), before)
        self.assertEqual(result[0].payload, struct.pack('>iBIIII', 0, 0, 0, 0, 0, 0))
        with self.assertRaises(ValueError):
            decompose(self.path, 1001, request(self.gear['uid']+1), 'once')
        self.assertEqual(self.dump(), before)

    def test_no_loss_on_invalid_or_unverified_inputs(self):
        fraction = self.grant(60100)
        potion = self.grant(77420)
        bad = [request(self.gear['uid'], self.gear['uid']), request(self.gear['uid'], special=1),
               request(fraction['uid']), request(potion['uid']), request(self.gear['uid']+999999), b'']
        for wire in bad:
            before = self.dump()
            with self.assertRaises(ValueError):
                decompose(self.path, 1001, wire, 'reject')
            self.assertEqual(self.dump(), before)
        before = self.dump()
        with self.assertRaises(ValueError):
            decompose(self.path, 1002, request(self.gear['uid']), 'foreign')
        self.assertEqual(self.dump(), before)

    def test_locked_damaged_and_equipped_rejected(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=10000 WHERE uid=1001')
        lock_item(self.path, 1001, struct.pack('>QhiB', self.gear['uid'], 1, 0, 0), 'lock')
        before = self.dump()
        with self.assertRaises(ValueError):
            decompose(self.path, 1001, request(self.gear['uid']), 'locked')
        self.assertEqual(self.dump(), before)
        gear = self.grant(30230)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE equipment_durability SET current=1 WHERE item_uid=?', (gear['uid'],))
        before = self.dump()
        with self.assertRaises(ValueError):
            decompose(self.path, 1001, request(gear['uid']), 'damaged')
        self.assertEqual(self.dump(), before)

    def test_full_material_bag_and_encoder_failure_roll_back_equipment(self):
        before = self.dump()
        with patch('els_server.storage.decomposition.decompose_ack', side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):
                decompose(self.path, 1001, request(self.gear['uid']), 'encoder')
        self.assertEqual(self.dump(), before)
        for _ in range(36):
            self.grant(135983, 99)
        before = self.dump()
        with self.assertRaises(ValueError):
            decompose(self.path, 1001, request(self.gear['uid']), 'full')
        self.assertEqual(self.dump(), before)

    def test_concurrent_retry_and_existing_crystal_stack(self):
        self.grant(701000, 90)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: decompose(self.path, 1001, request(self.gear['uid']), 'concurrent'), range(2)))
        self.assertEqual(self.crystals(), 126)
        self.assertEqual(len([i for i in self.items() if i['template'] == 701000]), 1)

    def test_real_dispatch_and_invalid_phase(self):
        session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
                               client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                               population_test=True, clear_test=True, reward_test=True, item_test=True)
        session.role, session.phase = 'game', 'dungeon_active'
        event = Event(0x202, kind=0x1c0, payload=request(self.gear['uid']))
        before = self.dump()
        self.assertEqual(struct.unpack_from('>i', session.handle(event, 100)[0].payload)[0], -1)
        self.assertEqual(self.dump(), before)
        session.phase = 'town_ready'
        self.assertEqual(session.handle(event, 101)[0].kind, 0x1c1)
        self.assertEqual(self.crystals(), 36)


if __name__ == '__main__':
    unittest.main()
