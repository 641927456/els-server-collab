"""Owned worker calls preserve auth/mail and leave activity work to periodic ticks."""
from contextlib import closing,ExitStack
import sqlite3
import tempfile
import time
from pathlib import Path
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import patch

from els_server.application import Application, FriendsSession
from els_server.config import ServerConfig
from els_server.domain.local_session import LocalSession,SessionOrderError
from els_server.protocol.protocol_codec import Event


class AuxiliaryWorkerActivityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = Application(ServerConfig(profile='bootstrap'))
        self.addCleanup(self.app.close)
        self.session = session = FriendsSession.__new__(FriendsSession)
        session.application = self.app
        session.released = session.social_overflow = False
        session.coop_error = None
        session.client_build = 'dx11_260923'
        session.role, session.phase = 'game', 'town_ready'
        session.identity = {'id': 2}
        session.account = SimpleNamespace(uid=1001, store=SimpleNamespace(uid=1001))
        self.app.playing[2] = session
        self.enabled, self.auth_reads = True, 0
        def enabled(identity):
            self.auth_reads += 1
            return self.enabled
        self.app.registry = SimpleNamespace(enabled=enabled)
        self.pending = [Event(0x201, kind=0x85, payload=b'pending')]
        def drain():
            result, self.pending = self.pending, []
            return result
        session.mailbox = SimpleNamespace(drain=drain)
        self.steps = []
        def observe(s):
            self.steps.append('clock')
        def after_reply(s, result):
            self.steps.append('after_reply')
            return result
        session.activity2026_awards = SimpleNamespace(
            online=SimpleNamespace(observe=observe), after_reply=after_reply,
            finalize=lambda s, result: result)

    def auxiliary(self, **changes):
        return Event(**(dict(event_id=0x202, kind=0x7d0, payload=bytes(9),
                             performers=(0,)) | changes))

    async def test_worker_burst_keeps_auth_and_pending_messages_without_activity_reads(self):
        expected = self.pending[:]
        self.assertEqual(await self.app.call(self.session.handle, self.auxiliary(), request_sequence=1), expected)
        for sequence in range(2, 130):
            self.assertEqual(await self.app.call(self.session.handle, self.auxiliary(), request_sequence=sequence), [])
        self.assertEqual(self.auth_reads, 129)
        self.assertEqual(self.steps, [])
        self.enabled = False
        with self.assertRaises(SessionOrderError):
            await self.app.call(self.session.handle, self.auxiliary(), request_sequence=130)
        self.assertEqual(self.auth_reads, 130)
        self.assertEqual(self.steps, [])

    async def test_real_business_and_nonmatching_envelopes_keep_clock_boundaries(self):
        answer = [Event(0x201, kind=0x21a, payload=bytes(36))]
        self.pending = []
        self.app.world.field_bosses.request = lambda s, event: answer
        for changes in ({'kind': 0x219}, {'payload': bytes(8)}, {'performers': ()},
                        {'uid': 1001}, {'target_uid': 1001}, {'payload_mode': 1}):
            self.steps.clear()
            self.assertEqual(await self.app.call(self.session.handle, self.auxiliary(**changes)), answer)
            self.assertEqual(self.steps, ['clock', 'clock', 'after_reply'])

    async def test_periodic_still_observes_before_and_after_and_emits_activity(self):
        def periodic_notifications(s):
            self.steps.append('periodic')
            return []
        self.session.periodic_notifications = MethodType(periodic_notifications, self.session)
        self.assertEqual(await self.app.call(self.session.periodic_notifications), [])
        self.assertEqual(self.steps, ['clock', 'periodic', 'clock', 'after_reply'])

    def periodic_fixture(self,stack,current):
        self.session.next_periodic=0
        self.pending=[]
        clock=SimpleNamespace(monotonic=lambda:current[0],perf_counter=time.perf_counter)
        stack.enter_context(patch('els_server.application.time',clock))
        stack.enter_context(patch('els_server.domain.session_auxiliary.time',clock,create=True))
        ticks=stack.enter_context(patch('els_server.domain.group_challenge.tick'))
        stack.enter_context(patch.object(self.app.world.field_bosses,'periodic'))
        stack.enter_context(patch.object(self.app.world.dungeons,'room',return_value=None))
        stack.enter_context(patch.object(self.app.world.dungeons,'periodic'))
        stack.enter_context(patch.object(LocalSession,'periodic_notifications',return_value=[]))
        stack.enter_context(patch('els_server.domain.resonance_flow.synchronize',side_effect=lambda s,m:m))
        stack.enter_context(patch('els_server.domain.companion_peer_sync.receive',return_value=[]))
        return ticks

    async def test_idle_periodic_polls_keep_room_ticks_but_not_activity_work(self):
        current=[100.0]
        with ExitStack()as stack:
            ticks=self.periodic_fixture(stack,current)
            await self.app.call(self.session.periodic_notifications)
            for i in range(1,100):
                current[0]=100+i/100
                self.assertEqual(await self.app.call(self.session.periodic_notifications),[])
            current[0]=101.0
            await self.app.call(self.session.periodic_notifications)
            self.assertEqual(ticks.call_count,101)
        self.assertEqual(self.steps,['clock','clock','after_reply']*2)

    async def test_idle_poll_preserves_pending_messages_and_external_revocation(self):
        current=[100.0]
        with ExitStack()as stack:
            self.periodic_fixture(stack,current)
            await self.app.call(self.session.periodic_notifications)
            self.steps.clear();current[0]=100.25
            expected=[Event(0x201,kind=0x85,payload=b'pending')]
            self.pending=expected[:]
            self.assertEqual(await self.app.call(self.session.periodic_notifications),expected)
            self.assertEqual(self.steps,['after_reply'])
            self.enabled=False
            with self.assertRaises(SessionOrderError):
                await self.app.call(self.session.periodic_notifications)

    async def test_pending_online_interval_commits_on_periodic_and_final_close(self):
        from els_server.domain.online_2026_clock import OnlineTitleClock
        from els_server.storage.online_2026_progress import OnlineTitleProgress
        runtime = Path(__import__('els_server').__file__).resolve().parents[1]
        pack = __import__('json').loads((runtime/'els_server/data/selected2026/local-pair.json').read_bytes())
        selection = (runtime/'els_server/data/selected2026'/pack['resources']['online_selection']['file']).read_bytes()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            path = Path(folder)/'own.sqlite3'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY,level INTEGER)')
                db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER)')
                db.execute('INSERT INTO characters VALUES(1001,99)')
                db.execute('INSERT INTO character_owners VALUES(1001,2)')
                db.commit();db.execute('BEGIN IMMEDIATE')
                repo = OnlineTitleProgress(db, selection, campaign='owned-latency')
                repo.initialize()
                repo.register_period(week=1, starts=100, ends=10000,
                                     purpose='explicit_local_test', provenance='Owned regression fixture')
            current = [100.0]
            clock = OnlineTitleClock(selection, campaign='owned-latency',
                eligibility=lambda s: (str(path), 2, 1001, 99),
                monotonic=lambda: current[0], epoch=lambda: current[0])
            self.session.activity2026_awards = SimpleNamespace(online=clock)
            with ExitStack()as stack:
                self.periodic_fixture(stack,current)
                await self.app.call(self.session.periodic_notifications)
                current[0] = 160.0
                await self.app.call(self.session.handle, self.auxiliary())
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM online2026_spans').fetchone()[0], 0)
                await self.app.call(self.session.periodic_notifications)
                # Repeated idle polls neither lose nor duplicate the interval.
                await self.app.call(self.session.periodic_notifications)
            current[0] = 170.0
            clock.observe(self.session, stop=True)
            current[0] = 200.0
            clock.observe(self.session)
            with closing(sqlite3.connect(path)) as db:
                progress = OnlineTitleProgress(db, selection, campaign='owned-latency').snapshot(
                    account=2, character=1001, week=1)
                self.assertEqual(progress['observed_online_seconds'], 70)
                self.assertEqual(db.execute('SELECT count(*) FROM online2026_spans').fetchone()[0], 2)

    @unittest.skipUnless(hasattr(Application, '_worker_call'), 'Materialized timing worker only')
    async def test_worker_reports_activity_stage_costs(self):
        from els_server.performance import capture_calls
        original = self.session.activity2026_awards.online.observe
        def observe(s):
            time.sleep(.006)
            original(s)
        self.session.activity2026_awards.online.observe = observe
        self.pending = []
        self.app.world.field_bosses.request = lambda s, event: []
        with capture_calls() as calls:
            await self.app.call(self.session.handle, self.auxiliary(kind=0x219))
        sample = calls[0]
        self.assertGreaterEqual(sample['clock_before_ms'], 5)
        self.assertGreaterEqual(sample['clock_after_ms'], 5)
        self.assertGreaterEqual(sample['handler_ms'], sample['clock_before_ms']+sample['clock_after_ms'])
        self.assertGreaterEqual(sample['domain_ms'], 0)
        self.assertGreaterEqual(sample['after_reply_ms'], 0)


if __name__ == '__main__':
    unittest.main()
