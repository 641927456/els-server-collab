import struct, tempfile, unittest
from pathlib import Path
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.storage.local_state import LocalState
from els_server.protocol.protocol_codec import Event


class QuestDialogueReplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()

    def test_unbound_npc_still_answers(self):
        from els_server.domain.quest_flow import handle
        s = LocalSession(self.account, enter_town=True, enter_dungeon=True, npc_slot_test=True,
                         gate_test=True, population_test=True, clear_test=True, reward_test=True,
                         item_test=True, client_build='dx11_260923')
        s.role = 'game'; s.phase = 'town_ready'
        reply = handle(s, Event(0x202, kind=0xfd, payload=struct.pack('>i', 99999)), 1)
        self.assertEqual([event.kind for event in reply], [0xfe])


if __name__ == '__main__':
    unittest.main()
