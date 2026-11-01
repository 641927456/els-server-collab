"""Current reset scroll variants use their existing native business messages."""
import sqlite3
import struct
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event
from els_server.storage import skill_traits
from els_server.storage.identification_ui import perform
from els_server.storage.inventory_state import grant_items, load_items
from els_server.storage.local_state import LocalState

IDENTIFICATION_SCROLLS = (287960, 287961, 710078, 710079, 710080, 710081)
FORGET_SCROLLS = (135667, 135668, 163100, 165727, 189218, 190625,
                  711711, 711712, 100003891, 100004932)


class ResetScrollTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'qa.sqlite3'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE characters SET level=20 WHERE uid=1001')
            db.execute('UPDATE reward_balances SET ed=2000000 WHERE uid=1001')
        self.session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
                                    client_build='dx11_260923', npc_slot_test=True,
                                    gate_test=True, population_test=True, clear_test=True,
                                    reward_test=True, item_test=True)
        self.session.role = 'game'
        self.session.phase = 'town_ready'

    def grant(self, template, count=1):
        item = client_data().item(template)
        with closing(sqlite3.connect(self.path)) as db, db:
            return grant_items(db, [dict(template=template, metadata=item['metadata'], group=4 if template in IDENTIFICATION_SCROLLS + FORGET_SCROLLS else 1, quantity=count)], 1001)[0]

    def items(self):
        with closing(sqlite3.connect(self.path)) as db:
            return load_items(db, 1001)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def select(self, operation):
        return skill_traits.choose(self.path, 1001, 1, struct.pack('>ii', 21000, 3), operation)

    def reset(self, item, operation, *, account=1, prepare=lambda db: None):
        payload = struct.pack('>iiQB', 21000, 3, item['uid'] if item else 0, 0 if item else 1)
        return skill_traits.reset(self.path, 1001, account, payload, operation, prepare=prepare)

    def test_all_blessed_variants_reset_identify_retry_and_cold_read(self):
        for template in IDENTIFICATION_SCROLLS:
            with self.subTest(template=template):
                gear = self.grant(61885)
                scroll = self.grant(template, 2)
                payload = struct.pack('>QQ', scroll['uid'], gear['uid'])
                op = 'identification-' + str(template)
                response = self.session.handle(Event(0x202, kind=0x43a, payload=payload), template)
                self.assertEqual((response[0].kind, struct.unpack_from('>i', response[0].payload)[0]), (0x43b, 0))
                perform(self.path, 1001, 0x438, struct.pack('>QBIi', gear['uid'], 0, 0, 0), op, lambda n: 0)
                current = next(i for i in self.items() if i['uid'] == gear['uid'])
                self.assertTrue(current['identified'])
                self.assertTrue(current['option_groups']['1'])
                before = self.dump()
                self.session.handle(Event(0x202, kind=0x43a, payload=payload), template)
                self.assertEqual(self.dump(), before)
                cold = LocalAccount(LocalState(self.path))
                self.assertEqual(next(i for i in cold.get_inventory_snapshot()['items'] if i['uid'] == gear['uid']), current)
                self.assertEqual(next(i['count'] for i in self.items() if i['uid'] == scroll['uid']), 1)
        self.assertEqual(self.account.get_reward_balances()['ed'], 2000000)

    def test_all_forget_variants_consume_once_without_ed(self):
        for template in FORGET_SCROLLS:
            with self.subTest(template=template):
                self.select('select-' + str(template))
                scroll = self.grant(template, 1)
                response = self.reset(scroll, 'reset-' + str(template))
                self.assertEqual(struct.unpack_from('>iiiiB', response.payload), (0, 0, 21000, 3, 0))
                self.assertEqual(struct.unpack_from('>I', response.payload, 17)[0], 1)
                self.assertFalse(self.account.character().get('skill_traits'))
                self.assertNotIn(scroll['uid'], [i['uid'] for i in self.items()])
                before = self.dump()
                self.reset(scroll, 'reset-' + str(template))
                self.assertEqual(self.dump(), before)
        self.assertEqual(self.account.get_reward_balances()['ed'], 2000000)

    def test_scroll_session_refresh_replay_after_reselection_and_cold_read(self):
        self.select('first')
        scroll = self.grant(711711, 3)
        payload = struct.pack('>iiQB', 21000, 3, scroll['uid'], 0)
        events = self.session.handle(Event(0x202, kind=0x55f, payload=payload), 1)
        self.assertEqual([e.kind for e in events], [0x560, 0xd9, 0x55b])
        self.assertEqual(struct.unpack_from('>i', events[0].payload)[0], 0)
        cold = LocalAccount(LocalState(self.path))
        cold.enable_characters()
        self.assertFalse(cold.character().get('skill_traits'))
        self.select('second')
        before = self.dump()
        self.session.handle(Event(0x202, kind=0x55f, payload=payload), 1)
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.account.character()['skill_traits'], {21000: 3})
        self.assertEqual(next(i['count'] for i in self.items() if i['uid'] == scroll['uid']), 2)

    def test_ed_payment_and_legacy_receipts_keep_their_shape(self):
        self.select('first')
        response = self.reset(None, 'ed')
        self.assertEqual(len(response.payload), 60)
        self.assertEqual(self.account.get_reward_balances()['ed'], 1500000)
        before = self.dump()
        self.reset(None, 'ed')
        self.assertEqual(self.dump(), before)

    def test_payment_and_session_envelope_rejections_are_atomic(self):
        self.select('first')
        scroll = self.grant(711711)
        before = self.dump()
        payload = struct.pack('>iiQB', 21000, 3, scroll['uid'], 0)
        for changes in ({'uid': 1234}, {'performers': (1,)}, {'payload_mode': 1}):
            events = self.session.handle(Event(0x202, kind=0x55f, payload=payload, **changes), 1)
            self.assertEqual(struct.unpack_from('>i', events[0].payload)[0], -1)
            self.assertEqual(self.dump(), before)
        from els_server.domain.skill_traits import reset_request
        for item_uid, use_ed in ((0, 0), (scroll['uid'], 1), (0, 2), (2**63, 0)):
            with self.assertRaises(ValueError):
                reset_request(struct.pack('>iiQB', 21000, 3, item_uid, use_ed))
        self.assertEqual(self.dump(), before)

    def test_invalid_locked_expired_and_foreign_scroll_leave_no_increment(self):
        self.select('first')
        invalid = self.grant(287960)
        scroll = self.grant(711711, 2)
        for item, account in ((invalid, 1), (scroll, 2), ({'uid': 123456789}, 1)):
            before = self.dump()
            with self.assertRaises(ValueError):
                self.reset(item, 'invalid', account=account)
            self.assertEqual(self.dump(), before)
        from els_server.storage.item_locks import assign as lock
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            lock(db, 1001, scroll['uid'], int(time.time()) + 3600)
        before = self.dump()
        with self.assertRaises(ValueError):
            self.reset(scroll, 'locked')
        self.assertEqual(self.dump(), before)
        expired = self.grant(190625)
        from els_server.storage.item_expiration import assign
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            assign(db, 1001, expired['uid'], int(time.time()) - 1)
        before = self.dump()
        with self.assertRaises(ValueError):
            self.reset(expired, 'expired')
        self.assertEqual(self.dump(), before)

    def test_encoder_and_refresh_failures_roll_back_scroll_and_trait(self):
        self.select('first')
        scroll = self.grant(711711)
        before = self.dump()
        with patch('els_server.protocol.protocol_codec.encode_event', side_effect=ValueError('encode')):
            with self.assertRaises(ValueError):
                self.reset(scroll, 'wire-failed')
        self.assertEqual(self.dump(), before)
        def failed(db):
            raise ValueError('refresh failed')
        with self.assertRaises(ValueError):
            self.reset(scroll, 'refresh-failed', prepare=failed)
        self.assertEqual(self.dump(), before)

    def test_concurrent_scroll_retry_is_one_debit(self):
        self.select('first')
        scroll = self.grant(711711, 3)
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda _: self.reset(scroll, 'same-request'), range(2)))
        self.assertEqual(next(i['count'] for i in self.items() if i['uid'] == scroll['uid']), 2)


if __name__ == '__main__':
    unittest.main()
