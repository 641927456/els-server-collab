import sqlite3, tempfile, unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.storage.local_state import LocalState


class RegionEntryFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.sqlite3'
        self.account = LocalAccount(LocalState(self.path)); self.account.enable_characters()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE characters SET unit_class=150,level=99')

    def session(self):
        s = LocalSession(self.account, enter_town=True, enter_dungeon=True, npc_slot_test=True,
                         gate_test=True, population_test=True, clear_test=True, reward_test=True,
                         item_test=True, client_build='dx11_260923')
        s.role = 'game'; s.phase = 'town_ready'
        return s

    def test_accepts_first_region_entry_once(self):
        from els_server.domain.region_entry_flow import periodic
        s = self.session()
        events = periodic(s)
        self.assertTrue(any(event.kind == 0xf0 for event in events))
        with closing(sqlite3.connect(self.path)) as db:
            quests = {row[0] for row in db.execute('SELECT quest FROM character_quests WHERE owner=1001')}
        self.assertIn(26640, quests)
        self.assertEqual(periodic(s), [])


if __name__ == '__main__':
    unittest.main()
