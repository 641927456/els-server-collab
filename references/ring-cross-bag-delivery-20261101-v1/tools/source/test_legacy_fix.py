"""Focused regression for the retained fashion helper after shared-plan repair."""
import importlib.util,json,sqlite3,struct,sys,tempfile,unittest
from contextlib import closing
from pathlib import Path
ROOT=Path('G:/els');OUT=Path(__file__).resolve().parent
BASE=ROOT/'releases/local/local-native-field-entry-identity-20261101-v1'
sys.dont_write_bytecode=True;sys.path.insert(0,str(BASE))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
spec=importlib.util.spec_from_file_location('fixed_fashion',OUT/'candidate-v2/els_server/domain/fashion_state.py')
fashion=importlib.util.module_from_spec(spec);spec.loader.exec_module(fashion)

class LegacyFixTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='owned-legacy-fix-',dir=OUT);self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'game.sqlite3';account=LocalAccount(LocalState(self.path));account.enable_characters()
        self.sql('INSERT INTO inventory_items VALUES(910001,1001,200700,0,1,7,0)')
        self.sql('INSERT INTO inventory_items VALUES(910002,1001,801154,0,1,9,49)')
    def sql(self,text,args=()):
        with closing(sqlite3.connect(self.path)) as db,db:return db.execute(text,args).fetchall()
    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:return load_items(db,1001)
    def send(self,a,b):return fashion.move_fashion(self.path,struct.pack('>BiBiB',*a,*b,0),1001)
    def test_failed_final_history_insert_rolls_back_all_three_positions(self):
        self.send((7,0),(9,49));self.send((27,0),(9,49));before=self.snapshot()
        history=self.sql('SELECT * FROM fashion_moves')
        self.sql("CREATE TRIGGER fail_history BEFORE INSERT ON fashion_moves BEGIN SELECT RAISE(ABORT,'owned rollback fixture'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'owned rollback fixture'):self.send((7,0),(9,49))
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.sql('SELECT * FROM fashion_moves'),history)
    def test_locked_timed_items_and_three_position_history_survive_cold_read(self):
        from els_server.storage.item_expiration import assign as expiry
        from els_server.storage.item_locks import assign as lock
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            for uid in (910001,910002):expiry(db,1001,uid,2100000000);lock(db,1001,uid,2100000000)
        original=self.snapshot();self.send((7,0),(9,49))
        before={i['uid']:{k:v for k,v in i.items()if k not in ('group','slot')} for i in original}
        after={i['uid']:{k:v for k,v in i.items()if k not in ('group','slot')} for i in self.snapshot()}
        self.assertEqual(before,after)
        self.assertEqual(len(json.loads(self.sql('SELECT after_json FROM fashion_moves')[0][0])),3)
        self.send((27,0),(9,49));self.assertEqual(self.snapshot(),original)
    def test_full_native_return_bag_refuses_without_changes(self):
        from els_server.storage.bag_capacity import grant_starting_fashion
        with closing(sqlite3.connect(self.path)) as db,db:
            grant_starting_fashion(db,1001)
            db.executemany('INSERT INTO inventory_items VALUES(?,1001,801154,0,1,27,?)',[(920000+s,s) for s in range(1120)])
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'outgoing costume bag full'):self.send((7,0),(9,49))
        self.assertEqual(self.snapshot(),before)
    def test_same_tab_swap_and_wrong_destination(self):
        self.sql('DELETE FROM inventory_items WHERE uid=910002')
        self.sql('INSERT INTO inventory_items VALUES(910002,1001,270977,0,1,9,49)')
        ack=self.send((7,0),(9,49));self.assertEqual(struct.unpack_from('>I',ack)[0],2)
        before=self.snapshot()
        for a,b in (((7,0),(9,43)),((9,49),(27,0))):
            with self.assertRaises(ValueError):self.send(a,b)
            self.assertEqual(self.snapshot(),before)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LegacyFixTests))
    (OUT/'legacy-fix-verification-v2.json').write_text(json.dumps(dict(passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),live_state_access=False,natural_GUI=False),indent=2)+'\n','utf8')
    sys.exit(not result.wasSuccessful())
