"""Costume lock lifetime and expanded native resale-based dismantling."""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain.fashion_state import move_fashion
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, FASHION_EQUIP_SLOTS
from els_server.domain.decomposition_rules import quote
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.inventory_management import lock_item, sort_inventory
from els_server.storage.inventory_actions import discard
from els_server.storage.decomposition import decompose


def lock_request(uid, days=1, action=0):return struct.pack('>QhiB', uid, days, action, 0)
def decompose_request(*uids):return struct.pack('>I', len(uids))+b''.join(struct.pack('>Q', u) for u in uids)+b'\0'


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'extension.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()
        other = self.account.characters.create('ExtOther', 5, 'other')['uid']
        self.other = self.account.for_character(other)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE reward_balances SET ed=1000000 WHERE uid=1001')

    def grant(self, template):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            return grant_items(db, [dict(template=template, metadata=VERIFIED_TEMPLATES[template],
                group=TEMPLATE_BAG_GROUPS[template], quantity=1)])[0]

    def items(self):
        with closing(sqlite3.connect(self.path)) as db:return load_items(db)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:return list(db.iterdump())

    def test_costume_and_accessory_lock_fee_reload_retry_and_discard(self):
        for template in (81021, 161665):
            item = self.grant(template)
            before = self.account.get_reward_balances()['ed']
            with patch('els_server.storage.inventory_management.time.time', return_value=2000000000):
                lock_item(self.path, 1001, lock_request(item['uid'], 2), 'lock-'+str(template))
            now = next(i for i in self.items() if i['uid']==item['uid'])
            self.assertEqual(now['lock_until'], 2000172800)
            self.assertEqual(self.account.get_reward_balances()['ed'], before-20000)
            after = self.dump()
            lock_item(self.path, 1001, lock_request(item['uid'], 2), 'lock-'+str(template))
            self.assertEqual(self.dump(), after)
            for payload in (lock_request(item['uid'], 1), lock_request(item['uid'], 0, 1)):
                with self.assertRaises(ValueError):lock_item(self.path, 1001, payload, 'early')
            with self.assertRaises(ValueError):discard(self.path, 1001, struct.pack('>Qi', item['uid'], 1), 'discard')
            self.assertEqual(self.dump(), after)
        self.assertEqual(LocalAccount(LocalState(self.path)).get_inventory_snapshot()['items'], self.items())

    def test_locked_costume_can_move_wear_sort_without_losing_lock(self):
        item = self.grant(81021)
        lock_item(self.path, 1001, lock_request(item['uid']), 'lock')
        move_fashion(self.path, struct.pack('>BiBiB', item['group'], item['slot'], 27, 19, 0))
        sort_inventory(self.path, 1001, b'', 'sort')
        bagged = next(i for i in self.items() if i['uid']==item['uid'])
        move_fashion(self.path, struct.pack('>BiBiB', bagged['group'], bagged['slot'], 9, FASHION_EQUIP_SLOTS[item['template']], 0))
        worn = next(i for i in self.items() if i['uid']==item['uid'])
        self.assertEqual((worn['group'], worn['lock_until']), (9, bagged['lock_until']))
        with closing(sqlite3.connect(self.path)) as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_expired_costume_lock_can_be_cleared_and_timed_costume_still_expires(self):
        from els_server.storage.item_expiration import assign, remove_due
        item = self.grant(81021)
        with patch('els_server.storage.inventory_management.time.time', return_value=1000000000):
            lock_item(self.path, 1001, lock_request(item['uid']), 'old-lock')
        lock_item(self.path, 1001, lock_request(item['uid'], 0, 1), 'unlock')
        self.assertNotIn('lock_until', next(i for i in self.items() if i['uid']==item['uid']))
        lock_item(self.path, 1001, lock_request(item['uid']), 'new-lock')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE'); assign(db, 1001, item['uid'], 2000000000)
        remove_due(self.path, 1001, now=2000000001)
        self.assertNotIn(item['uid'], {i['uid'] for i in self.items()})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertFalse(db.execute('SELECT 1 FROM item_locks WHERE item_uid=?', (item['uid'],)).fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_costume_lock_rejects_owner_funds_and_rolls_back_encoder_failure(self):
        item = self.grant(81021); before = self.dump()
        with self.assertRaises(ValueError):lock_item(self.path, self.other.uid, lock_request(item['uid']), 'other')
        with patch('els_server.storage.inventory_management.lock_ack', side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):lock_item(self.path, 1001, lock_request(item['uid']), 'wire')
        self.assertEqual(self.dump(), before)
        with closing(sqlite3.connect(self.path)) as db, db:db.execute('UPDATE reward_balances SET ed=0 WHERE uid=1001')
        before = self.dump()
        with self.assertRaises(ValueError):lock_item(self.path, 1001, lock_request(item['uid']), 'poor')
        self.assertEqual(self.dump(), before)

    def test_damaged_elite_and_normal_exact_yields_commit_together(self):
        ordinary = self.grant(30160); normal = self.grant(153740)
        with closing(sqlite3.connect(self.path)) as db, db:
            for item in (ordinary, normal):
                db.execute('UPDATE equipment_durability SET current=? WHERE item_uid=?', (item['durability']//2, item['uid']))
        sources = [i for i in self.items() if i['uid'] in (ordinary['uid'], normal['uid'])]
        self.assertEqual(sorted(quote(i)['quantity'] for i in sources), [5, 18])
        p = decompose_request(ordinary['uid'], normal['uid'])
        decompose(self.path, 1001, p, 'damaged-normal')
        self.assertEqual(sum(i['count'] for i in self.items() if i['template']==701000), 23)
        before = self.dump(); decompose(self.path, 1001, p, 'damaged-normal')
        self.assertEqual(self.dump(), before)
        self.assertEqual(LocalAccount(LocalState(self.path)).get_inventory_snapshot()['items'], self.items())

    def test_unverified_fraction_broken_and_high_level_rewards_keep_items(self):
        good = self.grant(153740); high = self.grant(30416); damaged = self.grant(30160)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE equipment_durability SET current=1 WHERE item_uid=?', (damaged['uid'],))
        for target in (high, damaged):
            before = self.dump()
            with self.assertRaises(ValueError):decompose(self.path, 1001, decompose_request(good['uid'], target['uid']), 'mixed')
            self.assertEqual(self.dump(), before)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE equipment_durability SET current=0 WHERE item_uid=?', (damaged['uid'],))
        before = self.dump()
        with self.assertRaises(ValueError):decompose(self.path, 1001, decompose_request(damaged['uid']), 'broken')
        self.assertEqual(self.dump(), before)

    def test_expanded_operations_use_the_existing_town_routes(self):
        costume = self.grant(81021); normal = self.grant(153740)
        s = LocalSession(self.account, enter_town=True, enter_dungeon=True, client_build='dx11_260923',
            npc_slot_test=True, gate_test=True, population_test=True, clear_test=True, reward_test=True, item_test=True)
        s.role, s.phase = 'game', 'town_ready'
        self.assertEqual(s.handle(Event(0x202, kind=0x663, payload=lock_request(costume['uid'])), 10)[0].kind, 0x664)
        response = s.handle(Event(0x202, kind=0x1c0, payload=decompose_request(normal['uid'])), 11)
        self.assertEqual((response[0].kind, struct.unpack_from('>i', response[0].payload)[0]), (0x1c1, 0))
        self.assertEqual(sum(i['count'] for i in self.items() if i['template']==701000), 10)


if __name__ == '__main__':unittest.main()
