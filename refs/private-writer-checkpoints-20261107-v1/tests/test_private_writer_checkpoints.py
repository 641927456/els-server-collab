"""Private connection checkpoint ownership, FULL atomicity and crash recovery."""
import bootstrap
from concurrent.futures import Future
from contextlib import closing,contextmanager
from pathlib import Path
import json,os,sqlite3,subprocess,sys,tempfile,threading,time,unittest
from unittest.mock import patch
from els_server.storage import wal_checkpoints as checkpoints
from els_server.storage.coin_writer import CoinWriter
from els_server.storage.death_writer import DeathWriter
from els_server.storage.clock_writer import ClockWriter
from els_server.storage.position_writer import PositionWriter
from els_server.storage.read_scope import ReadConnections
from els_server.storage.reward_state import RewardState
from els_server.domain.drop_pickup import GROUND_ED

NAMES={'els-coin-writer','els-death-writer','els-clock-writer','els-position-writer'}
def until(check):
    deadline=time.monotonic()+5
    while not check():
        if time.monotonic()>=deadline:raise AssertionError('Owned checkpoint deadline')
        time.sleep(.01)
def create(path):
    with closing(sqlite3.connect(path))as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE committed(id INTEGER PRIMARY KEY,value TEXT)')
        db.execute('CREATE TABLE linked(id INTEGER REFERENCES committed(id) DEFERRABLE INITIALLY DEFERRED)')
        db.execute('CREATE TABLE location(uid INTEGER PRIMARY KEY,town INTEGER,board INTEGER,progress INTEGER,x REAL,y REAL,z REAL,revision INTEGER)')
        db.execute('INSERT INTO location VALUES(1001,1,2,0,0,0,0,0)');db.commit()
@contextmanager
def service(path):
    worker=checkpoints.WALCheckpoints(path);worker.prepare()
    try:yield worker
    finally:worker.close()
def auto(db):return db.execute('PRAGMA wal_autocheckpoint').fetchone()[0]

class PrivateCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=bootstrap.HERE);self.path=Path(self.temp.name)/'owned.sqlite3';create(self.path)
    def tearDown(self):self.temp.cleanup()

    def four_writers(self,managed):
        owner=checkpoints.WALCheckpoints(self.path)if managed else None
        if owner is not None:owner.prepare()
        readers=ReadConnections();closed=[];connect=sqlite3.connect;writers=[];expected=0 if managed else 1000
        class Tracked(sqlite3.Connection):
            committed=False;private=False
            def execute(db,sql,*args,**kwargs):
                if db.private and db.committed and sql.startswith('PRAGMA wal_autocheckpoint='):
                    raise sqlite3.DatabaseError('owned post-commit policy failure')
                return super().execute(sql,*args,**kwargs)
            def commit(db):
                result=super().commit();db.committed=True;return result
            def __exit__(db,*args):
                result=super().__exit__(*args)
                if args[0]is None:db.committed=True
                return result
            def close(db):
                if db.private:
                    closed.append((threading.current_thread().name,super().execute('PRAGMA wal_autocheckpoint').fetchone()[0],super().execute('PRAGMA synchronous').fetchone()[0]))
                return super().close()
        def tracked(*args,**kwargs):
            kwargs['factory']=Tracked;db=connect(*args,**kwargs)
            db.private=threading.current_thread().name in NAMES and '?mode=rw'in str(args[0]);return db
        def record(db,index):
            self.assertTrue(db.in_transaction);self.assertEqual(auto(db),expected)
            self.assertEqual(db.execute('PRAGMA synchronous').fetchone(),(2,))
            db.execute("INSERT INTO committed VALUES(?,'owned')",(index,));return index
        try:
            with patch.object(sqlite3,'connect',tracked),patch.object(CoinWriter,'_grant',staticmethod(lambda db,job:record(db,job[4]))):
                coin=CoinWriter(self.path,checkpoints=owner);death=DeathWriter(self.path,readers,checkpoints=owner)
                clock=ClockWriter(self.path,checkpoints=owner);position=PositionWriter(self.path,checkpoints=owner)
                writers=[position,coin,death,clock]
                coin.prepare();death.prepare();clock.prepare()
                store=RewardState(self.path,1001,account_id=1)
                for index in (1,2):self.assertEqual(coin.claim(store,str(index),b'owned',drop_id=index,template=min(GROUND_ED),ed=1,dungeon=34710),index)
                for index in (3,4):self.assertEqual(death.submit(self.path,lambda db,index=index:record(db,index)),index)
                for index in (5,6):self.assertEqual(clock.commit(((self.path,lambda db,index=index:record(db,index)),),stop=True),((None,),None))
                position.save(self.path,1001,(1,2,0,2.,3.,4.));position.save(self.path,1001,(1,2,0,5.,6.,7.))
                for writer in writers:writer.close()
            self.assertEqual(len(closed),4);self.assertEqual({row[0]for row in closed},NAMES)
            self.assertTrue(all(row[1:]==(expected,2)for row in closed))
            with closing(connect(self.path))as cold:
                self.assertEqual(cold.execute('SELECT COUNT(*)FROM committed').fetchone(),(6,))
                self.assertEqual(cold.execute('SELECT x,y,z,revision FROM location').fetchone(),(5.,6.,7.,2))
        finally:
            for writer in writers:writer.close()
            readers.close()
            if owner is not None:owner.close()

    def test_managed_four_writers_FULL_lifetime_and_no_postcommit_policy_SQL(self):self.four_writers(True)
    def test_standalone_four_writers_keep_original_policy(self):self.four_writers(False)

    def test_managed_preparation_and_physical_commit_failures_have_no_increment(self):
        with service(self.path)as owner:
            readers=ReadConnections();writer=DeathWriter(self.path,readers,checkpoints=owner)
            def bad(db,physical):
                self.assertEqual(auto(db),0);db.execute("INSERT INTO committed VALUES(1,'owned')")
                if physical:db.execute('INSERT INTO linked VALUES(999)')
                else:raise ValueError('owned preparation failure')
            try:
                with self.assertRaisesRegex(ValueError,'owned preparation failure'):writer.submit(self.path,lambda db:bad(db,False))
                with self.assertRaises(sqlite3.IntegrityError):writer.submit(self.path,lambda db:bad(db,True))
                with closing(sqlite3.connect(self.path))as cold:self.assertEqual(cold.execute('SELECT COUNT(*)FROM committed').fetchone(),(0,))
                def good(db):db.execute("INSERT INTO committed VALUES(2,'owned')");return True
                self.assertTrue(writer.submit(self.path,good))
            finally:writer.close();readers.close()

    def test_not_ready_and_foreign_save_are_rejected_before_transaction(self):
        owner=checkpoints.WALCheckpoints(self.path);coin=CoinWriter(self.path,checkpoints=owner)
        try:
            with self.assertRaisesRegex(RuntimeError,'not ready'):coin.prepare()
        finally:coin.close();owner.close()
        other=self.path.with_name('other.sqlite3');create(other)
        with service(self.path)as owner:
            readers=ReadConnections();writer=DeathWriter(other,readers,checkpoints=owner)
            try:
                with self.assertRaisesRegex(ValueError,'binding changed'):writer.prepare()
                with closing(sqlite3.connect(other))as cold:self.assertEqual(cold.execute('SELECT COUNT(*)FROM committed').fetchone(),(0,))
            finally:writer.close();readers.close()

    def test_closed_owner_rejects_reused_private_connection(self):
        owner=checkpoints.WALCheckpoints(self.path);owner.prepare();readers=ReadConnections();writer=DeathWriter(self.path,readers,checkpoints=owner)
        try:
            writer.prepare();owner.close()
            with self.assertRaisesRegex(RuntimeError,'not running'):writer.submit(self.path,lambda db:db.execute("INSERT INTO committed VALUES(1,'bad')"))
            with closing(sqlite3.connect(self.path))as cold:self.assertEqual(cold.execute('SELECT COUNT(*)FROM committed').fetchone(),(0,))
        finally:writer.close();readers.close();owner.close()

    def test_failed_owner_rejects_reused_private_connection(self):
        connect=sqlite3.connect;fail=threading.Event()
        class Fault(sqlite3.Connection):
            def execute(self,sql,*args,**kwargs):
                if 'wal_checkpoint(PASSIVE)'in sql and fail.is_set():raise sqlite3.OperationalError('owned checkpoint failure')
                return super().execute(sql,*args,**kwargs)
        def traced(*args,**kwargs):
            if threading.current_thread().name=='els-wal-checkpoint':kwargs['factory']=Fault
            return connect(*args,**kwargs)
        owner=checkpoints.WALCheckpoints(self.path);readers=ReadConnections();writer=None
        with patch.object(checkpoints.sqlite3,'connect',traced):owner.prepare()
        try:
            writer=DeathWriter(self.path,readers,checkpoints=owner);writer.prepare();fail.set();until(owner.finished.done)
            with self.assertRaisesRegex(sqlite3.OperationalError,'owned checkpoint failure'):writer.submit(self.path,lambda db:db.execute("INSERT INTO committed VALUES(1,'bad')"))
            with closing(connect(self.path))as cold:self.assertEqual(cold.execute('SELECT COUNT(*)FROM committed').fetchone(),(0,))
        finally:
            if writer is not None:writer.close()
            readers.close()
            with self.assertRaisesRegex(sqlite3.OperationalError,'owned checkpoint failure'):owner.close()

    def test_reader_gap_drains_WAL_after_committed_writes(self):
        with service(self.path)as owner,closing(sqlite3.connect(self.path))as reader:
            readers=ReadConnections();writer=DeathWriter(self.path,readers,checkpoints=owner)
            try:
                reader.execute('BEGIN');self.assertEqual(reader.execute('SELECT COUNT(*)FROM committed').fetchone(),(0,));before=owner.runs
                for index in range(20):
                    def save(db,index=index):db.execute("INSERT INTO committed VALUES(?,'owned')",(index,));return index
                    self.assertEqual(writer.submit(self.path,save),index)
                until(lambda:owner.runs>before and owner.last[1]>owner.last[2])
                with closing(sqlite3.connect(self.path))as cold:self.assertEqual(cold.execute('SELECT COUNT(*)FROM committed').fetchone(),(20,))
                reader.rollback();until(lambda:owner.last[1]>=0 and owner.last[1]==owner.last[2])
            finally:writer.close();readers.close()

    def test_process_crash_recovers_FULL_private_writer_ACK(self):
        script=Path(__file__).resolve();code="import sys,runpy;sys.path.insert(0,"+repr(str(script.parent))+");runpy.run_path("+repr(str(script))+",run_name='__main__')"
        result=subprocess.run([sys.executable,'-B','-c',code,'--candidate','--child',str(self.path)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['committed'])
        with closing(sqlite3.connect(self.path))as cold:
            self.assertEqual(cold.execute('PRAGMA quick_check').fetchall(),[('ok',)])
            self.assertEqual(cold.execute('SELECT * FROM committed').fetchall(),[(1,'owned durable ACK')])
            with cold:cold.execute("INSERT OR IGNORE INTO committed VALUES(1,'owned durable ACK')")
            self.assertEqual(cold.execute('SELECT COUNT(*)FROM committed').fetchone(),(1,))

def crash_child(path):
    owner=checkpoints.WALCheckpoints(path);owner.prepare();reader=sqlite3.connect(path)
    reader.execute('BEGIN');reader.execute('SELECT * FROM committed').fetchall()
    readers=ReadConnections();writer=DeathWriter(path,readers,checkpoints=owner)
    def save(db):
        assert auto(db)==0 and db.execute('PRAGMA synchronous').fetchone()==(2,)
        db.execute("INSERT INTO committed VALUES(1,'owned durable ACK')");return True
    assert writer.submit(path,save);print(json.dumps(dict(committed=True)),flush=True);os._exit(0)

if __name__=='__main__':
    if '--child'in sys.argv:crash_child(Path(sys.argv[sys.argv.index('--child')+1]))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PrivateCheckpointTests))
    out=dict(passed=result.wasSuccessful(),tests=result.testsRun,source=bootstrap.SOURCE_BINDINGS,runtime=sys.version,GIL_enabled=getattr(sys,'_is_gil_enabled',lambda:True)(),
        scope='Owned SQLite/private writers, process-crash recovery and read-gap drain; no power-failure or WAN capacity claim')
    (bootstrap.HERE/'private-writer-checkpoints-tests.json').write_text(json.dumps(out,indent=2),'utf8')
    raise SystemExit(not result.wasSuccessful())
