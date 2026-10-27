from pathlib import Path
from contextlib import closing,contextmanager
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3,tempfile,time,unittest
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.storage.read_scope import committed_reads,snapshot_connection,quest_notification_projection
from els_server.storage.sqlite_timing import write_transaction,read_transaction
from els_server.storage.career_purchase_recovery import recover
from els_server.performance import worker_timing

ROOT=Path(__file__).resolve().parents[1]

class SelectionBusinessTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'state.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()

    def test_ineligible_recovery_never_reserves_writer_and_preserves_state(self):
        with closing(sqlite3.connect(self.path))as blocker:
            blocker.execute('BEGIN IMMEDIATE');sample={};started=time.perf_counter()
            with worker_timing(sample),committed_reads():
                self.assertEqual(recover(self.path,1001,1,prepare=lambda *a:None),dict(status='not_eligible'))
            self.assertLess(time.perf_counter()-started,.5)
            self.assertEqual(sample.get('sql_begin_wait_ms',0),0)
            blocker.rollback()

    def test_foreign_owner_is_rejected_in_read_probe_without_write(self):
        with closing(sqlite3.connect(self.path))as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            with self.assertRaisesRegex(ValueError,'owner mismatch'):
                recover(self.path,1001,2,prepare=lambda *a:None)

    def eligible(self):
        from els_server.domain.character_rules import CLASSES
        cls=next(k for k,v in CLASSES.items()if v['stage']==2 and v['base_class']==1)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE characters SET unit_class=?,level=99,transcendence=0 WHERE uid=1001',(cls,))

    def test_positive_probe_rechecks_after_writer_acquisition(self):
        self.eligible();calls=[]
        @contextmanager
        def changed(db):
            with closing(sqlite3.connect(self.path))as other,other:
                other.execute('UPDATE characters SET transcendence=1 WHERE uid=1001')
            with write_transaction(db):calls.append(True);yield db
        with patch('els_server.storage.career_purchase_recovery.write_transaction',changed):
            self.assertEqual(recover(self.path,1001,1,prepare=lambda *a:None),dict(status='not_eligible'))
        self.assertEqual(calls,[True])

    def test_positive_recovery_preserves_busy_and_reports_wait(self):
        self.eligible();connect=sqlite3.connect
        def bounded(*a,**kw):
            if not kw.get('uri'):kw['timeout']=.02
            return connect(*a,**kw)
        with closing(connect(self.path))as blocker:
            blocker.execute('BEGIN IMMEDIATE');sample={}
            with worker_timing(sample),patch('sqlite3.connect',bounded):
                with self.assertRaises(sqlite3.OperationalError):recover(self.path,1001,1,prepare=lambda *a:None)
            self.assertEqual(sample['sql_busy'],1);self.assertGreater(sample['sql_begin_wait_ms'],10)

    def test_paid_recovery_encoder_failure_rolls_back_then_applies_once(self):
        import json
        from els_server.storage.inventory_state import grant_items
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES
        self.eligible()
        with closing(sqlite3.connect(self.path))as db,db:
            item=grant_items(db,[dict(template=288319,metadata=VERIFIED_TEMPLATES[288319],quantity=1,group=4)],1001)[0]
            db.execute('CREATE TABLE shop_purchase_receipts(operation_id TEXT PRIMARY KEY,request_sha256 TEXT NOT NULL,cost INTEGER NOT NULL,response BLOB NOT NULL,items_json TEXT NOT NULL,balances_json TEXT NOT NULL)')
            db.execute('INSERT INTO shop_purchase_receipts VALUES(?,?,?,?,?,?)',('owned-paid-book','fixture',1,b'',json.dumps([item]),'{}'))
        def dump():
            with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())
        before=dump()
        def fail(*args):raise ValueError('owned encoder failure')
        with self.assertRaisesRegex(ValueError,'owned encoder failure'):recover(self.path,1001,1,prepare=fail)
        self.assertEqual(dump(),before)
        result=recover(self.path,1001,1,prepare=lambda *a:None);self.assertEqual(result['status'],'recovered')
        saved=dump();self.assertEqual(recover(self.path,1001,1,prepare=lambda *a:None)['status'],'not_eligible');self.assertEqual(dump(),saved)

    def test_readers_release_transactions_and_observe_external_state(self):
        from els_server.storage.ariel_cash import snapshot
        state=LocalState(self.path)
        with committed_reads():
            before=state.load();self.assertEqual(snapshot(self.path,1)['balance'],0)
            with closing(sqlite3.connect(self.path,timeout=.05))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE location SET progress=31 WHERE uid=1001')
            self.assertEqual(state.load()['progress'],31)
            self.assertNotEqual(state.load(),before)
            with snapshot_connection(self.path)as db:
                with self.assertRaises(sqlite3.OperationalError):db.execute('UPDATE location SET progress=99')

    def test_quest_reply_cache_invalidates_commit_second_and_owner(self):
        from els_server.storage.seal_quests import QuestState
        q=QuestState(self.path,1001,account_id=1);loads=[]
        def load():loads.append(True);return {'active':[{'id':len(loads)}],'completed':[]}
        with committed_reads(),patch('els_server.storage.read_scope.time.time',return_value=100):
            first=quest_notification_projection(q,load);first['active'].clear()
            self.assertEqual(len(quest_notification_projection(q,load)['active']),1);self.assertEqual(len(loads),1)
            with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE location SET progress=19 WHERE uid=1001')
            quest_notification_projection(q,load);self.assertEqual(len(loads),2)
            with patch('els_server.storage.read_scope.time.time',return_value=101):quest_notification_projection(q,load)
            self.assertEqual(len(loads),3)
            foreign=QuestState(self.path,1001,account_id=2);quest_notification_projection(foreign,load);self.assertEqual(len(loads),4)
        with committed_reads():quest_notification_projection(q,load)
        self.assertEqual(len(loads),5)

    def test_real_quest_snapshot_does_not_reuse_foreign_owner(self):
        from els_server.storage.seal_quests import QuestState
        with committed_reads():
            self.assertEqual(QuestState(self.path,1001,account_id=1).notification_snapshot(),dict(active=[],completed=[]))
            with self.assertRaises(ValueError):QuestState(self.path,1001,account_id=2).notification_snapshot()

    def test_query_only_projection_under_writer_and_error_cleanup(self):
        with closing(sqlite3.connect(self.path))as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            with closing(sqlite3.connect(self.path,timeout=.02))as db:
                db.execute('PRAGMA query_only=ON')
                with read_transaction(db):self.assertTrue(db.execute('SELECT uid FROM characters').fetchone())
                self.assertFalse(db.in_transaction)
                with self.assertRaises(sqlite3.OperationalError):
                    with read_transaction(db):db.execute('UPDATE characters SET level=99')
                self.assertFalse(db.in_transaction)
        with closing(sqlite3.connect(self.path))as db:
            with self.assertRaises(ValueError):
                with read_transaction(db):pass

if __name__=='__main__':unittest.main()
