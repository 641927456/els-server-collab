"""Force bar payload and result-screen dungeon retry."""
import sqlite3, struct, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.storage.local_state import LocalState
from els_server.protocol.dungeon_messages import skill_data
from els_server.protocol.protocol_codec import Event


class ForcePayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'state.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()

    def payload(self, **changes):
        character = dict(self.account.character(), **changes)
        return skill_data(self.account.get_skills(), character)

    def test_empty_force_inventory_sends_no_learned_skills(self):
        data = self.payload(force_inventory=[])
        self.assertEqual(data[-5:], b'\x00'*5)

    def test_owned_force_record_terminates_payload(self):
        data = self.payload(force_inventory=[{'skill': 900402, 'rank': 5, 'template': 295714}])
        self.assertTrue(data.endswith(struct.pack('>I', 1)+struct.pack('>iBiB', 900402, 5, 0, 0)+b'\0'))


class DungeonRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'state.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()
        self.session = LocalSession(self.account, enter_town=True, enter_dungeon=True,
                                    client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                                    population_test=True, clear_test=True, reward_test=True,
                                    item_test=True)
        self.session.role = 'game'; self.session.phase = 'dungeon_active'
        self.session.clear_notified = True; self.session.dungeon_id = 34050

    def test_cleared_result_accepts_new_selection(self):
        with patch('els_server.domain.region_quests.account_dungeon_allowed', return_value=True):
            reply = self.session.handle(Event(0x202, kind=0x7d4, payload=struct.pack('>ii', 1, 34050)), 1)
        self.assertEqual([e.kind for e in reply], [0x7d5])
        self.assertEqual(struct.unpack('>ii', reply[0].payload), (0, 1))
        self.assertEqual(self.session.requested_dungeon_id, 34050)

    def test_cleared_result_starts_the_run(self):
        opaque = struct.pack('>I', 1)+bytes(19)
        with patch('els_server.domain.region_quests.account_dungeon_allowed', return_value=True):
            reply = self.session.handle(Event(0x202, kind=0x382, payload=opaque), 2)
        self.assertEqual([e.kind for e in reply][:2], [0x383, 0x14a])
        self.assertEqual(self.session.phase, 'dungeon_loading')
        self.assertFalse(self.session.clear_notified)
        self.assertEqual(self.session.dungeon_id, 34050)


if __name__ == '__main__':
    unittest.main()
