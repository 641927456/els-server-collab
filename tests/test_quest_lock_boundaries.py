from pathlib import Path
from contextlib import closing,contextmanager
from unittest.mock import patch
import json,sqlite3,tempfile,time,unittest,uuid
from els_server.domain.local_session import LocalAccount
from els_server.domain.tutorial_quests import restore_initialization
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.storage.read_scope import committed_reads
from els_server.storage.sqlite_timing import write_transaction
from els_server.storage.reward_state import RewardState
from els_server.performance import worker_timing

ROOT=Path(__file__).resolve().parents[1]

class QuestLockBoundaries(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'own.sqlite3';self.a=LocalAccount(LocalState(self.path));self.a.enable_characters()
        self.q=QuestState(self.path,1001,account_id=1);self.q.snapshot();restore_initialization(self.q)
    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())

    def test_existing_tutorial_read_does_not_reserve_writer_or_change_wire(self):
        from els_server.protocol.quest_messages import initialization
        wanted=initialization(self.q.notification_snapshot()).payload;before=self.dump()
        with closing(sqlite3.connect(self.path))as blocker:
            blocker.execute('BEGIN IMMEDIATE');sample={};started=time.perf_counter()
            with worker_timing(sample),committed_reads():out,changed=restore_initialization(self.q)
            self.assertLess(time.perf_counter()-started,.5);self.assertFalse(changed)
            self.assertEqual(out.payload,wanted);self.assertEqual(sample.get('sql_begin_wait_ms',0),0)
        self.assertEqual(before,self.dump())

    def test_noop_live_restore_emits_only_current_snapshot_and_releases_read(self):
        with committed_reads():
            replies,changed=restore_initialization(self.q,live=True);self.assertFalse(changed)
            self.assertEqual([e.kind for e in replies],[0x2b])
            with closing(sqlite3.connect(self.path,timeout=.02))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE location SET progress=9 WHERE uid=1001')

    def test_missing_old_lazy_table_still_enters_original_writer(self):
        with closing(sqlite3.connect(self.path))as db,db:db.execute('DROP TABLE quest_progress_events')
        calls=[]
        @contextmanager
        def marked(db):
            calls.append(True)
            with write_transaction(db):yield db
        with patch('els_server.domain.tutorial_quests.write_transaction',marked):restore_initialization(self.q)
        self.assertEqual(calls,[True])
        with closing(sqlite3.connect(self.path))as db:self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE name='quest_progress_events'").fetchone())

    def test_possible_starter_rechecks_sql_after_writer_wait(self):
        with closing(sqlite3.connect(self.path))as db,db:
            rows=db.execute('SELECT * FROM character_quests WHERE owner=1001').fetchall();db.execute('DELETE FROM character_quests WHERE owner=1001')
        calls=[]
        @contextmanager
        def changed(db):
            with closing(sqlite3.connect(self.path))as other,other:
                other.executemany('INSERT INTO character_quests VALUES(?,?,?,?,?)',rows)
            calls.append(True)
            with write_transaction(db):yield db
        with patch('els_server.domain.tutorial_quests.write_transaction',changed):out,restored=restore_initialization(self.q)
        self.assertFalse(restored);self.assertEqual(calls,[True])
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('SELECT * FROM character_quests WHERE owner=1001').fetchall(),rows)

    def test_starter_encoding_failure_rolls_back_then_retries_once(self):
        with closing(sqlite3.connect(self.path))as db,db:db.execute('DELETE FROM character_quests WHERE owner=1001')
        before=self.dump()
        with patch('els_server.domain.tutorial_quests.wire.initialization',side_effect=ValueError('own encoding failure')):
            with self.assertRaisesRegex(ValueError,'own encoding failure'):restore_initialization(self.q)
        self.assertEqual(before,self.dump());self.assertTrue(restore_initialization(self.q)[1]);saved=self.dump()
        self.assertFalse(restore_initialization(self.q)[1]);self.assertEqual(saved,self.dump())

    def test_foreign_owner_cannot_use_read_preview(self):
        with self.assertRaises(ValueError):restore_initialization(QuestState(self.path,1001,account_id=2))

    def test_pending_deferred_edge_never_uses_noop_preview(self):
        from els_server.storage.epic_followups import deferred_write_possible
        from els_server.domain.seal_quests import quest_catalog,sequence
        cat=quest_catalog();parent=next(qid for qid,q in cat.quests.items()if q['m_eQuestType']==5 and any(i in cat.quests for i in sequence(q.get('m_iAfterQuestID',{}))))
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('DELETE FROM character_quests WHERE owner=1001');db.execute("INSERT INTO completed_quests VALUES(1001,?,1,'{}')",(parent,))
            self.assertTrue(deferred_write_possible(db,1001))
        calls=[]
        @contextmanager
        def marked(db):
            calls.append(True)
            with write_transaction(db):yield db
        with patch('els_server.domain.tutorial_quests.write_transaction',marked):restore_initialization(self.q)
        self.assertEqual(calls,[True])

    def test_idle_expiry_and_circuit_preview_do_not_reserve_writer(self):
        from els_server.storage.item_expiration import remove_due
        from els_server.storage.equipment_circuits import repair_missing
        with closing(sqlite3.connect(self.path))as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            with committed_reads():self.assertEqual(remove_due(self.path,1001),[]);self.assertEqual(repair_missing(self.path,1001),[])

    def test_positive_expiry_rechecks_deadline_under_writer(self):
        from els_server.storage.inventory_state import grant_items
        from els_server.storage.item_expiration import remove_due
        moment=int(time.time())
        with closing(sqlite3.connect(self.path))as db,db:item=grant_items(db,[dict(template=77000,metadata=2,group=6,quantity=1,expires_at=moment+10)])[0]
        @contextmanager
        def extended(db):
            with closing(sqlite3.connect(self.path))as other,other:other.execute('UPDATE item_expiration SET expires_at=? WHERE item_uid=?',(moment+100,item['uid']))
            with write_transaction(db):yield db
        with patch('els_server.storage.item_expiration.write_transaction',extended):self.assertEqual(remove_due(self.path,1001,now=moment+11),[])
        with closing(sqlite3.connect(self.path))as db:self.assertTrue(db.execute('SELECT 1 FROM inventory_items WHERE uid=?',(item['uid'],)).fetchone())

    def test_manual_reward_error_rolls_back_and_retry_stays_once_only(self):
        reward=RewardState(self.path);run=str(uuid.uuid4());before=self.dump();sample={}
        def fail(b):raise ValueError('owned reward encoding')
        with worker_timing(sample),self.assertRaisesRegex(ValueError,'owned reward encoding'):reward.grant(run,b'owned proof',7,9,fail)
        self.assertEqual(before,self.dump());self.assertEqual(sample['sql_rollbacks'],1)
        first=reward.grant(run,b'owned proof',7,9,lambda b:json.dumps(b).encode());after=self.dump()
        self.assertTrue(reward.grant(run,b'owned proof',7,9,lambda b:b'never rebuilt')['replayed']);self.assertEqual(after,self.dump());self.assertFalse(first['replayed'])

    def test_shared_reward_writer_is_not_committed_or_timed_as_a_new_writer(self):
        reward=RewardState(self.path);before=self.dump();sample={}
        with self.assertRaisesRegex(ValueError,'caller rollback'):
            with closing(sqlite3.connect(self.path))as db,db:
                db.execute('BEGIN IMMEDIATE')
                with worker_timing(sample):reward.grant(str(uuid.uuid4()),b'owned shared proof',7,9,lambda b:b'ack',transaction=db)
                self.assertTrue(db.in_transaction);self.assertEqual(sample.get('sql_begin_wait_ms',0),0)
                raise ValueError('caller rollback')
        self.assertEqual(before,self.dump())

    def test_manual_reward_busy_is_preserved_and_observed(self):
        reward=RewardState(self.path);connect=sqlite3.connect;sample={}
        with closing(connect(self.path))as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            with patch.object(reward,'_connect',side_effect=lambda:connect(self.path,timeout=.02)),worker_timing(sample):
                with self.assertRaises(sqlite3.OperationalError):reward.grant(str(uuid.uuid4()),b'owned waiting proof',7,9,lambda b:b'ack')
        self.assertEqual(sample['sql_busy'],1);self.assertGreater(sample['sql_begin_wait_ms'],10)

if __name__=='__main__':unittest.main()
