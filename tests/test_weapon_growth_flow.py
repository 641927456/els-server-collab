"""Real session dispatch and per-run weapon identity for native growth quests."""
import sqlite3
import struct
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain import weapon_growth_flow as flow
from els_server.domain import quest_flow
from els_server.protocol import weapon_growth_messages as wire
from els_server.protocol.protocol_codec import Event
from els_server.storage import weapon_growth as store
from els_server.storage.local_state import LocalState
from els_server.storage.reward_state import RewardState
from els_server.domain.local_artifact_rules import rating
from els_server.game_data import client_data


class WeaponGrowthFlowTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'save.db'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.account.get_inventory_snapshot()
        self.uid = 1002000
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE characters SET level=99 WHERE uid=1001')
            db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',
                       (self.uid, 1001, 136062, client_data().item(136062)['metadata'], 1, 9, 9))
        self.session = LocalSession(self.account, enter_town=True, client_build='dx11_260923')
        self.session.role = 'game'
        self.session.phase = 'town_ready'
        self.session.item_test = True

    def receipt(self, run='11111111-2222-4333-8444-555555555555', dungeon=34510):
        proof = (run + ':server-proof').encode()
        RewardState(self.path, 1001, account_id=1).grant(
            run, proof, 0, 0, response_builder=lambda balances, best: b'\0',
            dungeon_clear=(dungeon, 60), clear_assessment=rating(dungeon, 60, 1, 1, 1), artifact_base=0)
        return proof

    def request(self, sequence=10, flag=1):
        return quest_flow.handle(self.session, Event(0x202, kind=0x96c,
            payload=struct.pack('>iQB', 1, self.uid, flag)), sequence)

    def test_real_dispatch_claim_updates_options_and_next_native_task(self):
        proof = self.receipt()
        store.record_clear(self.path, 1001, 1, self.uid, '11111111-2222-4333-8444-555555555555', 34510, proof)
        for flag in (0, 1):
            reply = self.request(flag=flag)
            self.assertEqual([e.kind for e in reply], [0x96d, 0x96b])
            self.assertEqual(struct.unpack_from('>iiQ', reply[0].payload), (0, 1, self.uid))
            self.assertEqual(struct.unpack_from('>IiQQQ', reply[1].payload)[:2], (1, 2))
        self.assertEqual(self.account.get_inventory_snapshot()['items'][0]['option_groups']['17'], [200086])

    def test_login_snapshot_contains_owned_item_specific_task(self):
        event = quest_flow.initialization(self.session)
        self.assertEqual(event.kind, 0x2b)
        from els_server.storage.seal_quests import QuestState
        state = QuestState(self.path, 1001, account_id=1).snapshot()
        self.assertEqual(state['item_active'][0]['item_uid'], self.uid)
        self.assertEqual(state['item_active'][0]['objectives'], {1: 0})
        self.assertTrue(event.payload.endswith(wire.initialization_tail(state)))

    def test_session_generation_change_before_writer_rejects_without_reward(self):
        proof = self.receipt()
        store.record_clear(self.path, 1001, 1, self.uid, '11111111-2222-4333-8444-555555555555', 34510, proof)
        with closing(sqlite3.connect(self.path)) as db:
            before = list(db.iterdump())
        original = store.claim

        def changed_actor(*args, **kwargs):
            self.session.shop_session_id = 'changed-session-generation'
            return original(*args, **kwargs)

        with patch('els_server.storage.weapon_growth.claim', changed_actor):
            reply = self.request()
        self.assertEqual(struct.unpack_from('>i', reply[0].payload)[0], 2005)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(list(db.iterdump()), before)

    def test_incomplete_and_malformed_claim_return_native_failure(self):
        reply = self.request()
        self.assertEqual([e.kind for e in reply], [0x96d])
        self.assertEqual(struct.unpack_from('>i', reply[0].payload)[0], 2005)
        for payload in (b'', struct.pack('>iQB', 1, self.uid, 2)):
            reply = quest_flow.handle(self.session, Event(0x202, kind=0x96c, payload=payload), 20)
            self.assertEqual(struct.unpack_from('>i', reply[0].payload)[0], 2005)

    def test_native_progress_counts_committed_clear_and_does_not_poll_inventory_on_combat(self):
        s = self.session
        s.phase = 'dungeon_active'
        s.reward_test = True
        s.clear_notified = False
        run = SimpleNamespace(run_id='11111111-2222-4333-8444-555555555555', identity=34510, graph={'source_sha256': 'graph'})
        self.assertEqual(flow.observe(s, run, ()), [])
        with patch.object(self.account, 'get_inventory_snapshot', side_effect=AssertionError('idle inventory read')):
            self.assertEqual(flow.observe(s, run, (Event(0x201, kind=0xbd),)), [])
        self.receipt()
        s.clear_notified = True
        s.reward_receipt = {'run_id': run.run_id}
        reply = flow.observe(s, run, ())
        self.assertEqual([e.kind for e in reply], [0x96b])
        self.assertEqual(flow.observe(s, run, ()), [])

    def test_changing_weapon_back_during_run_does_not_restore_progress_eligibility(self):
        s = self.session
        s.phase = 'dungeon_active'
        s.reward_test = True
        s.clear_notified = False
        run = SimpleNamespace(run_id='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee', identity=34510, graph={'source_sha256': 'graph'})
        flow.observe(s, run, ())
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE inventory_items SET bag_group=1,slot=0 WHERE uid=?', (self.uid,))
        flow.observe(s, run, (Event(0x201, kind=0x105),))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE inventory_items SET bag_group=9,slot=9 WHERE uid=?', (self.uid,))
        flow.observe(s, run, (Event(0x201, kind=0x105),))
        self.receipt(run.run_id)
        s.clear_notified = True
        s.reward_receipt = {'run_id': run.run_id}
        self.assertEqual(flow.observe(s, run, ()), [])
        self.assertFalse(s._weapon_growth_run['eligible'])
        flow.observe(s, None, ())
        self.assertIsNone(s._weapon_growth_run)


if __name__ == '__main__':
    unittest.main()
