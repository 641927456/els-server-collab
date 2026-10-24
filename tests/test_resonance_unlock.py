"""Lv.99 auto-accept of the resonance unlock quest."""
import sqlite3, sys, tempfile, unittest
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.domain.resonance_unlock_flow import periodic
from els_server.storage.local_state import LocalState

def make_session(path):
    account=LocalAccount(LocalState(path));account.enable_characters()
    session=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
                         npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                         reward_test=True,item_test=True)
    session.role='game';session.phase='town_ready'
    return account,session

class ResonanceUnlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'state.sqlite3'

    def set_level(self,level):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=? WHERE uid=1001',(level,))

    def active(self):
        with closing(sqlite3.connect(self.path)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='character_quests'").fetchone():
                return []
            return [r[0] for r in db.execute('SELECT quest FROM character_quests WHERE owner=1001')]

    def test_accepts_once_at_level_99(self):
        account,session=make_session(self.path)
        self.set_level(98)
        self.assertEqual(periodic(session),[])
        self.assertNotIn(37100,self.active())
        self.set_level(99)
        events=periodic(session)
        self.assertEqual([e.kind for e in events],[0xf0])
        self.assertIn(37100,self.active())
        self.assertEqual(periodic(session),[])
        restored=LocalAccount(LocalState(self.path));restored.enable_characters()
        self.assertEqual(restored.character()['level'],99)

if __name__=='__main__':
    unittest.main()
