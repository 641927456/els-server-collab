"""Successful job-claim replay refreshes current career state without new rewards."""
import gc
import json
import sqlite3
import struct
import unittest
from contextlib import closing, contextmanager
from unittest.mock import patch

from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState
from tests import test_seal_quests as seal_fixtures


class CareerRetryTests(unittest.TestCase):
    QUESTS = (103030, 53672)

    @contextmanager
    def claim_case(self, qid):
        fixture = seal_fixtures.SealQuestTests('test_job_quest_class_change_rebuilds_career_context')
        fixture.setUp()
        try:
            if qid == 103030:
                fixture.set_class(1, 15)
                with closing(sqlite3.connect(fixture.path)) as db, db:
                    db.execute('INSERT OR REPLACE INTO completed_quests VALUES (?,?,?,?)',
                               (1001, 103020, 1, '{}'))
                fixture.action(0xee, qid)
                fixture.record('clear', 30182, rank=None)
                npc = 10008
            else:
                with closing(sqlite3.connect(fixture.path)) as db, db:
                    db.execute('UPDATE characters SET unit_type=15,unit_class=205,level=20 WHERE uid=1001')
                    for prior in (53670, 53671):
                        db.execute('INSERT OR REPLACE INTO completed_quests VALUES (?,?,?,?)',
                                   (1001, prior, 1, '{}'))
                fixture.action(0xee, qid)
                with closing(sqlite3.connect(fixture.path)) as db, db:
                    db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=?',
                               (json.dumps({28030: 1}), 1001, qid))
                npc = 10394
            event = Event(0x202, performers=(0,), kind=0xf4,
                          payload=struct.pack('>iiI5B', qid, npc, 0, 0, 0, 1, 1, 0))
            fixture.seq += 1
            yield fixture, event, fixture.seq
        finally:
            # All test-owned SQLite handles use closing(); collect any fixture
            # cycles before TemporaryDirectory cleanup on Windows.
            gc.collect()
            fixture.doCleanups()

    def persistent_state(self, fixture):
        with closing(sqlite3.connect(fixture.path)) as db:
            tables = sorted(name for name, in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'") if name != 'quest_actions')
            return {name: db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                    for name in tables}

    def assert_career(self, fixture, replies):
        notices = [e for e in replies if e.kind == 0x29f]
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].payload[21:23],
                         struct.pack('>H', fixture.a.character()['unit_class']))
        self.assertEqual([e.kind for e in replies[:4]], [0xf5, 0x2b, 0x29f, 0x55b])

    def test_same_and_new_sequence_retry_refresh_once_without_mutating_rewards(self):
        for qid in self.QUESTS:
            with self.subTest(quest=qid), self.claim_case(qid) as (fixture, event, sequence):
                self.assert_career(fixture, fixture.s.handle(event, sequence))
                before = self.persistent_state(fixture)
                full_before = fixture.dump()
                with patch('els_server.storage.careers.apply_quest_transition',
                           side_effect=AssertionError('replay must not repeat career transition')):
                    self.assert_career(fixture, fixture.s.handle(event, sequence))
                    self.assertEqual(fixture.dump(), full_before)
                    self.assert_career(fixture, fixture.s.handle(event, sequence + 1))
                self.assertEqual(self.persistent_state(fixture), before)

    def test_reopened_legacy_receipt_refreshes_without_schema_or_receipt_changes(self):
        for qid in self.QUESTS:
            with self.subTest(quest=qid), self.claim_case(qid) as (fixture, event, sequence):
                fixture.s.handle(event, sequence)
                before = self.persistent_state(fixture)
                with closing(sqlite3.connect(fixture.path)) as db:
                    raw = db.execute('SELECT reward_json FROM completed_quests WHERE owner=? AND quest=?',
                                     (1001, qid)).fetchone()[0]
                self.assertNotIn('career_refresh', json.loads(raw))
                fixture.a = LocalAccount(LocalState(fixture.path))
                fixture.a.enable_characters()
                fixture.s = LocalSession(fixture.a, enter_town=True, client_build='dx11_260923')
                fixture.s.item_test = True
                fixture.s.role = 'game'
                fixture.s.phase = 'town_ready'
                self.assert_career(fixture, fixture.s.handle(event, sequence))
                self.assertEqual(self.persistent_state(fixture), before)

    def test_retry_encodes_current_class_instead_of_restoring_old_quest_target(self):
        for qid, later in ((103030, 11), (53672, 93)):
            with self.subTest(quest=qid), self.claim_case(qid) as (fixture, event, sequence):
                fixture.s.handle(event, sequence)
                fixture.set_class(later, 35)
                before = self.persistent_state(fixture)
                self.assert_career(fixture, fixture.s.handle(event, sequence + 1))
                self.assertEqual(fixture.a.character()['unit_class'], later)
                self.assertEqual(self.persistent_state(fixture), before)

    def test_conflicting_and_unearned_claims_do_not_emit_career_refresh(self):
        for qid in self.QUESTS:
            with self.subTest(quest=qid), self.claim_case(qid) as (fixture, event, sequence):
                with closing(sqlite3.connect(fixture.path)) as db, db:
                    db.execute('DELETE FROM character_quests WHERE owner=? AND quest=?', (1001, qid))
                before = fixture.dump()
                replies = fixture.s.handle(event, sequence)
                self.assertFalse(any(e.kind == 0x29f for e in replies))
                self.assertNotEqual(replies[0].payload[:4], bytes(4))
                self.assertEqual(fixture.dump(), before)
            with self.subTest(quest=qid, conflict=True), self.claim_case(qid) as (fixture, event, sequence):
                fixture.s.handle(event, sequence)
                before = fixture.dump()
                changed = Event(0x202, performers=(0,), kind=0xf4,
                                payload=event.payload[:4]+struct.pack('>i', 12345)+event.payload[8:])
                replies = fixture.s.handle(changed, sequence)
                self.assertFalse(any(e.kind == 0x29f for e in replies))
                self.assertNotEqual(replies[0].payload[:4], bytes(4))
                self.assertEqual(fixture.dump(), before)

    def test_noncareer_completed_quest_does_not_gain_career_notification(self):
        with self.claim_case(53672) as (fixture, event, sequence):
            with closing(sqlite3.connect(fixture.path)) as db, db:
                db.execute('INSERT OR REPLACE INTO completed_quests VALUES (?,?,?,?)',
                           (1001, 28110, 1, json.dumps(dict(items=[], consumed_positions=[]))))
            before = self.persistent_state(fixture)
            normal = Event(0x202, performers=(0,), kind=0xf4,
                           payload=struct.pack('>iiI5B', 28110, 0, 0, 0, 0, 1, 1, 0))
            replies = fixture.s.handle(normal, sequence)
            self.assertFalse(any(e.kind == 0x29f for e in replies))
            self.assertEqual(self.persistent_state(fixture), before)

    def test_first_claim_career_encoding_failure_rolls_back_then_can_retry(self):
        for qid in self.QUESTS:
            with self.subTest(quest=qid), self.claim_case(qid) as (fixture, event, sequence):
                before = fixture.dump()
                with patch('els_server.protocol.career_messages.career_notice',
                           side_effect=RuntimeError('controlled career encoding failure')):
                    with self.assertRaisesRegex(RuntimeError, 'controlled career encoding failure'):
                        fixture.s.handle(event, sequence)
                self.assertEqual(fixture.dump(), before)
                self.assert_career(fixture, fixture.s.handle(event, sequence))

    def test_retry_career_encoding_failure_leaves_no_partial_action_or_reward(self):
        for qid in self.QUESTS:
            with self.subTest(quest=qid), self.claim_case(qid) as (fixture, event, sequence):
                fixture.s.handle(event, sequence)
                before = fixture.dump()
                with patch('els_server.protocol.career_messages.career_notice',
                           side_effect=RuntimeError('controlled replay encoding failure')):
                    with self.assertRaisesRegex(RuntimeError, 'controlled replay encoding failure'):
                        fixture.s.handle(event, sequence + 1)
                self.assertEqual(fixture.dump(), before)
                self.assert_career(fixture, fixture.s.handle(event, sequence + 1))


if __name__ == '__main__':
    unittest.main()
