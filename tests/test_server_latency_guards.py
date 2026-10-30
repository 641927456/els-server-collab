"""Run against a materialized performance channel, never a production save."""
import asyncio
from contextlib import closing
from dataclasses import replace
import json
import importlib.util
import logging
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from els_server.application import Application
from els_server.config import ServerConfig
from els_server.domain.local_session import LocalSession, LocalAccount
from els_server.observability import EventLog
from els_server.performance import capture_calls, local_auxiliary_noop
from els_server.protocol.protocol_codec import Event
from els_server.storage.accounts import Accounts
from els_server.storage.local_state import LocalState
from els_server.storage.read_scope import committed_reads, role_projection


ROOT=Path(__file__).resolve().parents[1]

def auxiliary(**changes):
    return Event(**(dict(event_id=0x202, kind=0x7d0, payload=bytes(9), performers=(0,)) | changes))


@unittest.skipUnless('local_auxiliary_noop' in LocalSession.handle.__code__.co_names, 'LOCAL dispatch overlay only')
class LocalAuxiliaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.app = Application(ServerConfig(profile='bootstrap'))
        self.addCleanup(self.app.close)
        self.app.account = LocalAccount(LocalState(Path(self.temp.name) / 'save.sqlite3'))
        self.session = await self.app.session()
        self.session.client_build = 'dx11_260923'
        self.session.role = 'game'
        self.session.phase = 'town_ready'

    async def test_burst_keeps_selected_profile_activity_policy(self):
        observed = []
        self.session.activity2026_awards = SimpleNamespace(online=SimpleNamespace(observe=lambda s: observed.append(s)))
        with patch.object(self.session, 'expiration_notifications', side_effect=AssertionError('ordinary path')):
            for _ in range(513):
                self.assertEqual(await self.app.call(self.session.handle, auxiliary()), [])
        expected = 0 if importlib.util.find_spec('els_server.domain.session_auxiliary') is not None else 1026
        self.assertEqual(len(observed), expected)
        self.session.phase = 'dungeon_active'
        self.assertTrue(local_auxiliary_noop(self.session, auxiliary()))

    async def test_nonmatching_envelopes_keep_original_path(self):
        changes = ({'kind': 0x113}, {'payload': bytes(8)}, {'payload': bytes(10)},
                   {'event_id': 0x201}, {'performers': ()}, {'uid': 1001},
                   {'target_uid': 1001}, {'payload_mode': 1})
        for values in changes:
            with self.subTest(values=values), patch.object(self.session, 'expiration_notifications', side_effect=RuntimeError('ordinary')):
                with self.assertRaisesRegex(RuntimeError, 'ordinary'):
                    self.session.handle(auxiliary(**values))

    async def test_binding_release_actor_mode_and_duplicate_guards(self):
        self.assertTrue(local_auxiliary_noop(self.session, auxiliary()))
        other = await self.app.session()
        other.role = 'game'; other.phase = 'town_ready'
        self.assertFalse(local_auxiliary_noop(self.session, auxiliary()))
        await self.app.release(other)
        self.assertTrue(local_auxiliary_noop(self.session, auxiliary()))
        self.session.account.store.uid += 1
        self.assertFalse(local_auxiliary_noop(self.session, auxiliary()))
        self.session.account.store.uid -= 1
        for field, value in (('role', 'frontend'), ('phase', 'dungeon_loading'), ('client_build', 'legacy'), ('_aux_local_live', False)):
            old = getattr(self.session, field)
            setattr(self.session, field, value)
            self.assertFalse(local_auxiliary_noop(self.session, auxiliary()))
            setattr(self.session, field, old)
        await self.app.release(self.session)
        self.assertFalse(local_auxiliary_noop(self.session, auxiliary()))


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'accounts.sqlite3'
        self.registry = Accounts(self.path)
        self.addCleanup(self.registry.close)
        self.identity = self.registry.create('qa_reader')

    def test_one_connection_but_fresh_queries_and_immediate_external_revocation(self):
        original = sqlite3.connect
        with patch('sqlite3.connect', wraps=original) as connect:
            for _ in range(1000):
                self.assertTrue(self.registry.enabled(self.identity['id']))
            self.assertEqual(connect.call_count, 1)
        with closing(original(self.path)) as writer, writer:
            writer.execute('UPDATE accounts SET enabled=0')
        self.assertFalse(self.registry.enabled(self.identity['id']))
        with closing(original(self.path)) as writer, writer:
            writer.execute('UPDATE accounts SET enabled=1')
        self.assertTrue(self.registry.enabled(self.identity['id']))
        self.assertFalse(self.registry.enabled(999999))
        self.assertFalse(self.registry._enabled_reader.in_transaction)
        with self.assertRaises(sqlite3.OperationalError):
            self.registry._enabled_reader.execute('UPDATE accounts SET enabled=0')

    def test_other_thread_cannot_reuse_reader_or_cache_permission(self):
        self.assertTrue(self.registry.enabled(self.identity['id']))
        self.registry.disable('qa_reader')
        result = []
        thread = threading.Thread(target=lambda: result.append(self.registry.enabled(self.identity['id'])))
        thread.start(); thread.join()
        self.assertEqual(result, [False])
        self.assertFalse(self.registry.enabled(self.identity['id']))

    def test_close_reopens_and_file_identity_replacement_is_not_stale(self):
        self.assertTrue(self.registry.enabled(self.identity['id']))
        self.registry.close(); self.registry.close()
        self.assertTrue(self.registry.enabled(self.identity['id']))
        old = self.registry._enabled_file
        # Windows forbids replacing an open SQLite file: exercise the identity
        # detector with the same fail-closed branch without touching live data.
        self.registry._enabled_file = ('old-device', 'old-inode')
        self.registry.disable('qa_reader')
        self.assertFalse(self.registry.enabled(self.identity['id']))
        self.assertEqual(self.registry._enabled_file, old)


class QueueTimingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = Application(ServerConfig(profile='bootstrap'))
        self.addCleanup(self.app.close)

    async def test_queue_wait_is_distinct_from_handler_and_keyword_arguments_work(self):
        started = threading.Event(); release = threading.Event()
        def blocker():
            started.set(); release.wait(2)
        first = asyncio.create_task(self.app.call(blocker))
        while not started.is_set():
            await asyncio.sleep(.001)
        with capture_calls() as samples:
            second = asyncio.create_task(self.app.call(lambda *, answer: answer, answer=42))
            await asyncio.sleep(.04)
            release.set()
            self.assertEqual(await second, 42)
        await first
        self.assertEqual(len(samples), 1)
        self.assertGreaterEqual(samples[0]['queue_ms'], 25)
        self.assertLess(samples[0]['handler_ms'], samples[0]['queue_ms'])
        self.assertFalse(samples[0]['failed'])

    async def test_exception_is_counted_and_does_not_poison_next_operation(self):
        def fail():
            raise ValueError('expected')
        with capture_calls() as samples:
            with self.assertRaisesRegex(ValueError, 'expected'):
                await self.app.call(fail)
            self.assertEqual(await self.app.call(lambda: 'next'), 'next')
        self.assertEqual([s['failed'] for s in samples], [True, False])
        self.assertEqual(self.app.performance.snapshot()['other']['errors'], 1)

    async def test_reader_closes_on_worker_and_close_is_idempotent(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            self.app.registry = await self.app.call(Accounts, Path(folder) / 'accounts.sqlite3')
            identity = await self.app.call(self.app.registry.create, 'qa_close')
            self.assertTrue(await self.app.call(self.app.registry.enabled, identity['id']))
            self.app.close(); self.app.close()
            self.assertIsNone(self.app.registry._enabled_reader)

    async def test_cancelled_wait_does_not_interrupt_running_transaction(self):
        begun = threading.Event(); release = threading.Event()
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / 'ledger.sqlite3'
            def write():
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute('CREATE TABLE ledger(value INTEGER)')
                    begun.set(); release.wait(2)
                    db.execute('INSERT INTO ledger VALUES (123)')
            task = asyncio.create_task(self.app.call(write))
            while not begun.is_set():
                await asyncio.sleep(.001)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            release.set()
            await self.app.call(lambda: None)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT value FROM ledger').fetchall(), [(123,)])

    async def test_projection_and_registry_costs_are_scoped(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / 'role.sqlite3'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE role(value INTEGER)'); db.execute('INSERT INTO role VALUES (7)')
            account = SimpleNamespace(store=SimpleNamespace(path=path), account_id=2, uid=1001, characters=object())
            def operation():
                def load():
                    with closing(sqlite3.connect(path)) as db:
                        return db.execute('SELECT value FROM role').fetchone()[0]
                first = role_projection(account, load)
                return first, role_projection(account, load)
            with capture_calls() as samples:
                self.assertEqual(await self.app.call(operation), (7, 7))
            self.assertEqual(samples[0]['projection_loads'], 1)
            self.assertEqual(samples[0]['projection_hits'], 1)
            self.assertGreater(samples[0]['projection_ms'], 0)


class LogTests(unittest.TestCase):
    def test_slow_sink_runs_on_log_thread_and_shutdown_drains(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            log = EventLog(ServerConfig(log_dir=Path(folder)))
            callers = []
            original = log.logger.info
            def slow(line):
                callers.append(threading.current_thread().name)
                time.sleep(.005)
                original(line)
            with patch.object(log.logger, 'info', side_effect=slow):
                start = time.perf_counter()
                for i in range(20):
                    log('request_timing', sequence=i)
                self.assertLess(time.perf_counter() - start, .05)
                log.close(); log.close()
            self.assertEqual(set(callers), {'els-event-log'})
            rows = [json.loads(s) for s in (Path(folder) / 'server.jsonl').read_text(encoding='utf8').splitlines()]
            self.assertEqual([r['sequence'] for r in rows], list(range(20)))

    def test_overflow_is_bounded_and_errors_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            log = EventLog(ServerConfig(log_dir=Path(folder), log_max_bytes=10000000))
            blocked = threading.Event(); release = threading.Event(); lines = []
            original = log.logger.info
            def sink(line):
                if threading.current_thread().name == 'els-event-log' and not blocked.is_set():
                    blocked.set(); release.wait(3)
                lines.append(json.loads(line))
            with patch.object(log.logger, 'info', side_effect=sink):
                log('listening')
                self.assertTrue(blocked.wait(1))
                for i in range(5000):
                    log('client_request', sequence=i)
                self.assertEqual(log.queue.qsize(), 4096)
                log('worker_error', error='controlled')
                release.set(); log.close()
            self.assertTrue(any(r['event'] == 'worker_error' for r in lines))
            overflow = [r for r in lines if r['event'] == 'log_overflow']
            self.assertEqual(sum(r['dropped'].get('client_request', 0) for r in overflow), 904)
            self.assertFalse(log.worker.is_alive())


if __name__ == '__main__':
    unittest.main()
