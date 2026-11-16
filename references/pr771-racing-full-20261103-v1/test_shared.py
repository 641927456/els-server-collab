"""The changed shared room codec and world teardown preserve old behavior."""
from pathlib import Path
import importlib.util,json,sys,types,unittest
ROOT=Path('G:/els');B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime';G=B/'git';W=Path(__file__).resolve().parent
sys.path.insert(0,str(R))
from els_server.protocol import dungeon_messages,social_messages
def previous(rel):
    rows={r['path']:r for r in json.loads((G/'references/pr771-racing-reset-20261103-v1/combined-files.json').read_bytes())['files']}
    old=G/rows[rel]['archive']/'online'/rel if rel in rows else ROOT/'releases/online/native-entry-boost-reward-sync-20261102-v1'/rel
    m=types.ModuleType('old_'+Path(rel).stem);m.__file__=str(old);exec(compile(old.read_text('utf8'),str(old),'exec'),m.__dict__);return m
class Wire(unittest.TestCase):
    def test_ordinary_room_and_full_user_bytes_are_preserved(self):
        old=previous('els_server/protocol/dungeon_messages.py')
        for map_id in(30000,30050):
            for port in(None,21500):
                self.assertEqual(dungeon_messages.room_info(map_id,bootstrap_port=port),old.room_info(map_id,bootstrap_port=port))
        self.assertEqual(dungeon_messages.member(dungeon_messages.DEFAULT_SLOTS),old.member(old.DEFAULT_SLOTS))
    def test_ordinary_party_capacity_remains_four_and_racing_six(self):
        old=previous('els_server/protocol/social_messages.py')
        for size in range(1,5):self.assertEqual(social_messages.party_info(10001,size),old.party_info(10001,size))
        with self.assertRaises(ValueError):social_messages.party_info(10001,5)
        self.assertEqual(social_messages.party_info(10001,6,150060,name='')[14],6)
saved=list(sys.argv);sys.argv=[sys.argv[0],'--runtime-root',str(R),'--temp-dir',str(W/'tmp')]
try:
    path=G/'tests/test_world_teardown_faults.py';spec=importlib.util.spec_from_file_location('existing_world_faults',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
finally:sys.argv=saved
class CurrentWorld(m.WorldCleanup):
    def session(self,identity,uid):
        s=super().session(identity,uid);s.account.account_id=identity;return s
def load_tests(loader,tests,pattern):
    suite=loader.loadTestsFromTestCase(Wire);suite.addTests(loader.loadTestsFromTestCase(CurrentWorld));return suite
