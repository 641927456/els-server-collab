"""Source-only disconnect regressions; synthetic temporary SQL and socket fixtures."""
import asyncio,sqlite3,sys,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.application import Application,FriendsSession
from els_server.transport import GameServer
from els_server.domain import mount_flow

class ReleaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'save.sqlite3'
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE mount_runtime(uid INTEGER PRIMARY KEY)')
            db.execute('CREATE TABLE companion_active(owner INTEGER PRIMARY KEY,mount INTEGER,mounted INTEGER)')
            db.execute('INSERT INTO companion_active VALUES(1001,50001,1)')
        self.app=Application.__new__(Application)
        self.app.executor=ThreadPoolExecutor(max_workers=1);self.addCleanup(self.app.executor.shutdown,wait=True)
        self.app.playing={};self.members=set();self.timer_calls=[]
        self.app.world=SimpleNamespace(disconnect=lambda s:self.members.discard(s))
        self.session=FriendsSession.__new__(FriendsSession)
        self.session.application=self.app;self.session.identity={'id':23};self.session.released=False
        self.session.account=SimpleNamespace(uid=1001,store=SimpleNamespace(path=self.path))
        self.session.mount_owner=1001;self.session.mount_touched=True
        self.session.activity2026_awards=SimpleNamespace(online=SimpleNamespace(observe=lambda s,stop=False:self.timer_calls.append(stop)))
        self.app.playing[23]=self.session;self.members.add(self.session)

    async def test_real_sqlite_write_lock_does_not_strand_playing_lease(self):
        connect=sqlite3.connect
        with closing(connect(self.path)) as locked:
            locked.execute('BEGIN IMMEDIATE')
            # Only the test's SQLite lock wait is shortened; the real tick and
            # transaction statements execute, no business result is mocked.
            with patch('els_server.storage.mount_state.sqlite3.connect',side_effect=lambda *a,**k:connect(*a,**dict(k,timeout=.05))):
                with self.assertRaisesRegex(sqlite3.OperationalError,'locked'):
                    await self.app.release(self.session)
            locked.rollback()
        self.assertNotIn(23,self.app.playing)
        self.assertNotIn(self.session,self.members)
        self.assertTrue(self.session.released)
        self.assertEqual(self.timer_calls,[True])
        with closing(connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT * FROM companion_active').fetchall(),[(1001,50001,1)])

    async def test_world_failure_still_releases_matching_lease(self):
        self.session.mount_touched=False
        def fail(s):raise OSError('world teardown failure')
        self.app.world.disconnect=fail
        with self.assertRaisesRegex(OSError,'world teardown failure'):
            await self.app.release(self.session)
        self.assertNotIn(23,self.app.playing);self.assertTrue(self.session.released)

    async def test_timer_failure_does_not_strand_lease(self):
        self.session.mount_touched=False
        def fail(s,stop=False):raise OSError('timer teardown failure')
        self.session.activity2026_awards.online.observe=fail
        with self.assertRaisesRegex(OSError,'timer teardown failure'):
            await self.app.release(self.session)
        self.assertNotIn(23,self.app.playing);self.assertTrue(self.session.released)

    async def test_stale_session_does_not_remove_newer_lease(self):
        self.session.mount_touched=False;other=object();self.app.playing[23]=other
        await self.app.release(self.session)
        self.assertIs(self.app.playing[23],other);self.assertTrue(self.session.released)
        await self.app.release(self.session)
        self.assertIs(self.app.playing[23],other)

    async def test_cancellation_during_persistence_still_finishes_worker_cleanup(self):
        entered=threading.Event();proceed=threading.Event()
        def persist(session):
            entered.set()
            if not proceed.wait(2):raise AssertionError('test did not release persistence barrier')
        with patch.object(mount_flow,'close',side_effect=persist):
            task=asyncio.create_task(self.app.release(self.session))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
            finally:proceed.set()
            # Queue a no-op on that same single worker, after persisted work.
            await self.app.call(lambda:None)
        self.assertNotIn(23,self.app.playing);self.assertNotIn(self.session,self.members)
        self.assertTrue(self.session.released);self.assertEqual(self.timer_calls,[True])

    async def test_queued_cleanup_survives_cancellation_before_worker_starts(self):
        entered=threading.Event();proceed=threading.Event();self.session.mount_touched=False
        def busy():
            entered.set()
            if not proceed.wait(2):raise AssertionError('busy worker barrier timed out')
        busy_task=asyncio.create_task(self.app.call(busy))
        self.assertTrue(await asyncio.to_thread(entered.wait,2))
        task=asyncio.create_task(self.app.release(self.session))
        await asyncio.sleep(.03)
        try:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        finally:proceed.set()
        await busy_task;await self.app.call(lambda:None)
        self.assertNotIn(23,self.app.playing);self.assertTrue(self.session.released)
        self.assertEqual(self.timer_calls,[True])

    async def test_cancelled_cleanup_failure_is_reported_without_swallowing(self):
        entered=threading.Event();proceed=threading.Event();loop=asyncio.get_running_loop();errors=[]
        previous=loop.get_exception_handler();loop.set_exception_handler(lambda loop,context:errors.append(context))
        def persist(session):
            entered.set()
            if not proceed.wait(2):raise AssertionError('test persistence barrier timed out')
            raise sqlite3.OperationalError('cancelled cleanup persistence failure')
        try:
            with patch.object(mount_flow,'close',side_effect=persist):
                task=asyncio.create_task(self.app.release(self.session))
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
                proceed.set();await self.app.call(lambda:None)
                for _ in range(4):await asyncio.sleep(0)
            self.assertNotIn(23,self.app.playing);self.assertTrue(self.session.released)
            self.assertEqual(len(errors),1)
            self.assertIsInstance(errors[0].get('exception'),sqlite3.OperationalError)
            self.assertIn('cancelled cleanup persistence failure',str(errors[0]['exception']))
        finally:proceed.set();loop.set_exception_handler(previous)

class Writer:
    def __init__(self):self.closed=0;self.waited=0
    def write(self,wire):pass
    async def drain(self):pass
    def close(self):self.closed+=1
    async def wait_closed(self):self.waited+=1

class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,fail):
        server=GameServer.__new__(GameServer);writer=Writer()
        # A plain object session is hashable and only passed through cleanup.
        class Business:phase='town_ready'
        session=Business()
        server.config=SimpleNamespace(mode='local',write_timeout=.2)
        server.probe_port=1;server.local_sessions=set();server.closing=False;server.metrics={'responses':0}
        logs=[];server.log=lambda event,**fields:logs.append(event)
        async def make(**kw):return session
        async def release(s):
            self.assertIs(s,session)
            if fail:raise sqlite3.OperationalError('release failure')
        async def read(reader):raise asyncio.IncompleteReadError(b'',1)
        server.application=SimpleNamespace(session=make,release=release);server.read_frame=read
        if fail:
            with self.assertRaisesRegex(sqlite3.OperationalError,'release failure'):
                await server.handle(None,writer,12)
        else:await server.handle(None,writer,12)
        self.assertEqual(writer.closed,1);self.assertEqual(writer.waited,1)
        self.assertEqual(server.local_sessions,set());self.assertIn('connection_finished',logs)

    async def test_notification_gather_cancellation_still_releases_and_closes(self):
        server=GameServer.__new__(GameServer);writer=Writer();released=[]
        class Business:phase='town_ready'
        business=Business()
        server.config=SimpleNamespace(mode='local',write_timeout=.2)
        server.probe_port=1;server.local_sessions=set();server.closing=False;server.metrics={'responses':0}
        server.log=lambda *args,**kw:None
        async def make(**kw):return business
        async def release(session):released.append(session)
        async def read(reader):raise asyncio.IncompleteReadError(b'',1)
        server.application=SimpleNamespace(session=make,release=release);server.read_frame=read
        original=asyncio.gather;observed=[]
        task=asyncio.create_task(server.handle(None,writer,70))
        def cancel_at_gather(*tasks,**kw):
            if asyncio.current_task() is task:
                observed.append(True);asyncio.get_running_loop().call_soon(task.cancel)
            return original(*tasks,**kw)
        with patch('els_server.transport.asyncio.gather',side_effect=cancel_at_gather):
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(observed,[True]);self.assertTrue(task.cancelled())
        self.assertEqual(released,[business]);self.assertEqual(server.local_sessions,set())
        self.assertEqual((writer.closed,writer.waited),(1,1))

    async def test_failed_release_always_closes_transport(self):await self.exercise(True)
    async def test_successful_release_closes_transport(self):await self.exercise(False)

if __name__=='__main__':unittest.main(verbosity=2)
