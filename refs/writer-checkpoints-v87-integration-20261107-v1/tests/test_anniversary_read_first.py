"""Actual owned couples, weekly mail, competing writer and physical rollback."""
import bootstrap
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import hashlib,json,sqlite3,struct,sys,tempfile,unittest
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage import relationships,relationship_mail as mail
from els_server.protocol import relationship_messages as wire
from els_server.protocol.social_messages import wstring
from els_server.storage.inventory_state import grant_items

BASELINE='--baseline'in sys.argv
NOW=1900000000

class AnniversaryReadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='own-anniversary-',dir=bootstrap.HERE)
        self.path=Path(self.temp.name)/'own.sqlite3';prepare(self.path)
        self.people=[]
        for account_id,name,unit in ((1,'OwnPairA',1),(2,'OwnPairB',2)):
            roster=Characters(self.path,account_id);uid=roster.create(name,unit,'own-create-'+str(account_id))['uid']
            account=LocalAccount(LocalState(self.path,uid),account_id=account_id)
            account.enable_characters(characters=roster);account.get_inventory_snapshot()
            self.people.append((uid,account_id,name))
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone(),('wal',))
    def tearDown(self):self.temp.cleanup()
    def sql(self):
        with closing(sqlite3.connect(self.path))as db:return list(db.iterdump())
    def pair(self):
        a,aa,an=self.people[0];b,ba,bn=self.people[1]
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=1)],a)
            relationships.propose(db,a,aa,b,ba,'own-A','own-B',wire.descriptor(bn),'own-proposal',guard=lambda db:None,encode=lambda *args:[],now=NOW)
            body=struct.pack('>bQ',0,a)+wstring(an)+struct.pack('>QBH',0,0,0)+struct.pack('>Q',b)+wstring(bn)+bytes(1)+wire.descriptor(bn)
            relationships.answer(db,b,ba,a,aa,'own-B','own-A',body,'own-accept',guard=lambda db:None,encode=lambda *args:[],now=NOW)
            self.assertEqual(relationships.snapshot(db,a,aa)['peer_uid'],b)
    def test_unpaired_does_not_reserve_writer(self):
        uid,aid,_=self.people[0];connect=sqlite3.connect;writes=[]
        class Observed(sqlite3.Connection):
            def execute(db,sql,*args,**kwargs):
                if sql=='BEGIN IMMEDIATE':writes.append(True)
                return super().execute(sql,*args,**kwargs)
        def traced(*args,**kwargs):return connect(*args,**kwargs,factory=Observed)
        with closing(connect(self.path))as holder:
            holder.execute('BEGIN IMMEDIATE')
            with patch.object(sqlite3,'connect',traced),ThreadPoolExecutor(max_workers=1)as pool:
                future=pool.submit(mail.maintenance,self.path,aid,uid,now=NOW)
                if BASELINE:
                    with self.assertRaises(sqlite3.OperationalError):future.result(timeout=3)
                    self.assertEqual(writes,[True])
                else:
                    self.assertEqual(future.result(timeout=3),[]);self.assertEqual(writes,[])
            holder.rollback()
    def test_original_owner_errors_are_preserved(self):
        uid,aid,_=self.people[0]
        with self.assertRaisesRegex(ValueError,'cold owner'):mail.maintenance(self.path,aid+10,uid,now=NOW)
        with self.assertRaisesRegex(ValueError,'character missing'):mail.maintenance(self.path,aid,999999999,now=NOW)
    def test_partial_relationship_schema_is_rejected(self):
        with closing(sqlite3.connect(self.path))as db,db:db.execute('CREATE TABLE native_couple_pairs_v1(id TEXT)')
        uid,aid,_=self.people[0]
        with self.assertRaisesRegex(ValueError,'Unknown or partial'):mail.maintenance(self.path,aid,uid,now=NOW)
    def test_actual_couple_first_week_and_idempotent_mail(self):
        self.pair();uid,aid,_=self.people[0]
        self.assertEqual(mail.maintenance(self.path,aid,uid,now=NOW+86400),[])
        first=mail.maintenance(self.path,aid,uid,now=NOW+8*86400);self.assertEqual(len(first),1)
        before=self.sql();self.assertEqual(mail.maintenance(self.path,aid,uid,now=NOW+8*86400),[]);self.assertEqual(self.sql(),before)
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('SELECT recipient_uid,mail_type,template FROM native_relationship_mail').fetchall(),[(uid,22,160762)])
            self.assertEqual(db.execute('SELECT COUNT(*)FROM game_mail').fetchone(),(1,))
    def test_real_commit_failure_rolls_back_mail_then_retry_issues_once(self):
        self.pair();uid,aid,_=self.people[0]
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('CREATE TABLE owned_commit_failure(owner INTEGER REFERENCES characters(uid) DEFERRABLE INITIALLY DEFERRED)')
        before=self.sql();connect=sqlite3.connect
        class Fault(sqlite3.Connection):
            def execute(db,sql,*args,**kwargs):
                result=super().execute(sql,*args,**kwargs)
                if sql.startswith('INSERT INTO native_relationship_mail'):
                    super().execute('INSERT INTO owned_commit_failure VALUES(999999999)')
                return result
        def faulty(*args,**kwargs):return connect(*args,**kwargs,factory=Fault)
        with patch.object(sqlite3,'connect',faulty),self.assertRaises(sqlite3.IntegrityError):
            mail.maintenance(self.path,aid,uid,now=NOW+8*86400)
        self.assertEqual(self.sql(),before)
        self.assertEqual(len(mail.maintenance(self.path,aid,uid,now=NOW+8*86400)),1)
        self.assertEqual(mail.maintenance(self.path,aid,uid,now=NOW+8*86400),[])
    def test_coupled_reward_still_requires_the_writer(self):
        self.pair();uid,aid,_=self.people[0];before=self.sql()
        with closing(sqlite3.connect(self.path))as holder:
            holder.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.OperationalError):mail.maintenance(self.path,aid,uid,now=NOW+8*86400)
            holder.rollback()
        self.assertEqual(self.sql(),before)

if __name__=='__main__':
    suite=unittest.TestSuite([AnniversaryReadTests('test_unpaired_does_not_reserve_writer')])if BASELINE else unittest.defaultTestLoader.loadTestsFromTestCase(AnniversaryReadTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    out=dict(passed=result.wasSuccessful(),tests=result.testsRun,baseline_bug_reproduced=BASELINE,source=bootstrap.SOURCE_BINDINGS,
        runtime=sys.version,GIL_enabled=sys._is_gil_enabled(),actual_mutual_couple_receipts=not BASELINE,actual_SQLite_deferred_commit_failure=not BASELINE,
        owned_temporary_directories_removed=True,production_installed=False)
    (bootstrap.HERE/('anniversary-baseline-tests.json'if BASELINE else'anniversary-read-first-tests.json')).write_text(json.dumps(out,indent=2),'utf8')
    raise SystemExit(not result.wasSuccessful())
