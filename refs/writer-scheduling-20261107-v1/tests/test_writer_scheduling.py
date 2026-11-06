"""Real SQLite turn ordering; helper rows isolate scheduling from gameplay."""
import bootstrap
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import json,sqlite3,tempfile,threading,time,unittest
from unittest.mock import patch
from els_server.storage.sqlite_timing import _WriterTurn,write_transaction,_writer_turn,begin_write,commit_write,end_write
from els_server.storage.death_writer import DeathWriter
from els_server.storage.coin_writer import CoinWriter
from els_server.storage.read_scope import ReadConnections
from els_server.storage.reward_state import RewardState
from els_server.domain.drop_pickup import GROUND_ED


def until(check):
    deadline=time.monotonic()+5
    while not check():
        if time.monotonic()>=deadline:raise AssertionError('Owned synchronization deadline')
        time.sleep(.001)


class WriterSchedulingTests(unittest.TestCase):
    def test_contended_batch_yields_without_reordering_or_early_reply(self):
        for lane in ('death','coin'):
            with self.subTest(lane=lane),tempfile.TemporaryDirectory(dir=bootstrap.HERE) as folder:
                path=Path(folder)/'game.sqlite3'
                with closing(sqlite3.connect(path)) as db:
                    db.execute('PRAGMA journal_mode=WAL')
                    db.execute('CREATE TABLE results(value INTEGER PRIMARY KEY)');db.commit()
                    self.assertEqual(db.execute('PRAGMA synchronous').fetchone(),(2,))
                readers=ReadConnections()
                writer=DeathWriter(path,readers) if lane=='death' else CoinWriter(path)
                entered=threading.Event();release=threading.Event()
                rival_entered=threading.Event();rival_release=threading.Event()
                ordered=[];seen=[];times={}
                store=RewardState(path,1001,account_id=1)
                def prepare(db,index):
                    ordered.append(index)
                    db.execute('INSERT INTO results VALUES(?)',(index,))
                    if index==0:
                        entered.set();self.assertTrue(release.wait(5))
                    return index
                def claim(index):
                    if lane=='death':return writer.submit(path,lambda db:prepare(db,index))
                    return writer.claim(store,str(index),b'owned-order',drop_id=index,
                        template=min(GROUND_ED),ed=1,dungeon=34710)
                def grant(db,job):return prepare(db,job[4])
                def rival():
                    with closing(sqlite3.connect(path,timeout=5)) as db:
                        turn=_writer_turn(db)
                        with write_transaction(db):
                            times['rival']=time.perf_counter()
                            seen.extend(row[0]for row in db.execute('SELECT value FROM results ORDER BY value'))
                            rival_entered.set();self.assertTrue(rival_release.wait(5))
                    return turn
                manager=patch.object(CoinWriter,'_grant',staticmethod(grant))
                try:
                    with manager,ThreadPoolExecutor(max_workers=12) as pool:
                        try:
                            # Queue the entire ready batch before its BEGIN,
                            # including close's sentinel. A yielded suffix
                            # must retire before that sentinel, in FIFO order.
                            blocker=sqlite3.connect(path,timeout=5);lease=begin_write(blocker)
                            jobs=[pool.submit(claim,0)]
                            until(lambda:_writer_turn(blocker).contended())
                            for index in range(1,9):
                                jobs.append(pool.submit(claim,index))
                                until(lambda:writer.queue.qsize()==index)
                            contender=pool.submit(rival)
                            turn=_writer_turn(blocker)
                            def three_waiters():
                                with turn.lock:return len(turn.waiters)==3
                            until(three_waiters)
                            close_job=pool.submit(writer.close);until(lambda:writer.closed)
                            commit_write(blocker);end_write(lease);blocker.close();blocker=None
                            self.assertTrue(entered.wait(5))
                            with closing(sqlite3.connect(path)) as observer:
                                turn=_writer_turn(observer)
                                until(turn.contended)
                                # Ensure the first job has consumed the soft slice.
                                time.sleep(.006)
                                times['release']=time.perf_counter();release.set()
                                self.assertTrue(rival_entered.wait(5))
                                self.assertEqual(seen,[0])
                                until(jobs[0].done)
                                self.assertEqual(jobs[0].result(),0)
                                self.assertTrue(all(not job.done()for job in jobs[1:]))
                                self.assertFalse(close_job.done())
                                self.assertEqual(observer.execute('SELECT value FROM results').fetchall(),[(0,)])
                                rival_release.set();contender.result(5)
                            self.assertEqual([job.result(5)for job in jobs],list(range(9)))
                            self.assertEqual(ordered,list(range(9)))
                            close_job.result(5);self.assertFalse(writer.thread.is_alive())
                        finally:
                            release.set();rival_release.set()
                            if blocker is not None:
                                blocker.rollback();end_write(lease,failed=True);blocker.close()
                    with closing(sqlite3.connect(path)) as observer:
                        self.assertEqual(observer.execute('SELECT value FROM results ORDER BY value').fetchall(),[(i,)for i in range(9)])
                    self.assertEqual(writer.snapshot()['batches'],2)
                    evidence.append(dict(lane=lane,remaining_jobs_stayed_queued=8,
                        rival_wait_after_first_release_ms=round(1000*(times['rival']-times['release']),3),
                        FIFO=True,cold_SQL=True,FULL=True,reply_after_commit=True))
                finally:release.set();rival_release.set();writer.close();readers.close()

    def test_uncontended_ready_jobs_keep_group_commit(self):
        with tempfile.TemporaryDirectory(dir=bootstrap.HERE) as folder:
            path=Path(folder)/'game.sqlite3'
            with closing(sqlite3.connect(path)) as db:db.execute('CREATE TABLE results(value INTEGER)')
            readers=ReadConnections();writer=DeathWriter(path,readers)
            started=threading.Event();release=threading.Event()
            def call(index):
                def prepare(db):
                    if index==0:started.set();self.assertTrue(release.wait(5))
                    db.execute('INSERT INTO results VALUES(?)',(index,));return index
                return writer.submit(path,prepare)
            try:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    try:
                        jobs=[pool.submit(call,0)];self.assertTrue(started.wait(5))
                        jobs.extend(pool.submit(call,i)for i in range(1,8))
                        until(lambda:writer.queue.qsize()==7);time.sleep(.006);release.set()
                        self.assertEqual(sorted(job.result(5)for job in jobs),list(range(8)))
                    finally:release.set()
                self.assertEqual(writer.batches,1);self.assertEqual(writer.maximum_batch,8)
            finally:release.set();writer.close();readers.close()

    def test_timeout_removes_only_waiter_and_new_arrival_cannot_cut_in(self):
        turn=_WriterTurn();owner=turn.enter(time.monotonic()+5)
        entered=threading.Event();finish=threading.Event();order=[]
        def timed():
            with self.assertRaises(sqlite3.OperationalError):turn.enter(time.monotonic()+.03)
        def surviving():
            ticket=turn.enter(time.monotonic()+5)
            try:order.append('waiting');entered.set();self.assertTrue(finish.wait(5))
            finally:turn.leave(ticket)
        with ThreadPoolExecutor(max_workers=3) as pool:
            expired=pool.submit(timed);expired.result(5)
            self.assertFalse(turn.contended())
            next_job=pool.submit(surviving);until(turn.contended)
            turn.leave(owner);self.assertTrue(entered.wait(5))
            def newcomer():
                ticket=turn.enter(time.monotonic()+5)
                try:order.append('new')
                finally:turn.leave(ticket)
            last=pool.submit(newcomer);until(turn.contended);finish.set()
            next_job.result(5);last.result(5)
        self.assertEqual(order,['waiting','new']);self.assertFalse(turn.active)


if __name__=='__main__':
    evidence=[]
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(WriterSchedulingTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    out=dict(passed=result.wasSuccessful(),tests=result.testsRun,scenarios=evidence,
        runtime=__import__('sys').version,candidate=bootstrap.SOURCE_BINDINGS,
        scope='Owned SQLite scheduling only; no native or public capacity claim')
    (bootstrap.HERE/'writer-scheduling-tests.json').write_text(json.dumps(out,indent=2),'utf8')
    raise SystemExit(not result.wasSuccessful())
