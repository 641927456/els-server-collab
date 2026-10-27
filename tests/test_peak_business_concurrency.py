import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

from els_server.business_queue import BoundedBusinessQueue
from els_server.performance import worker_timing, OperationMetrics
from els_server.storage.sqlite_timing import write_transaction, commit_write


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.queue = BoundedBusinessQueue(self.pool)
        self.gate = threading.Event()
        self.tasks = []

    async def asyncTearDown(self):
        self.gate.set()
        self.queue.close()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.pool.shutdown(wait=True, cancel_futures=True)
        await asyncio.sleep(0)

    def submit(self, fn):
        task = asyncio.create_task(self.queue.run(fn))
        self.tasks.append(task)
        return task

    async def until(self, fn):
        async with asyncio.timeout(3):
            while not fn():
                await asyncio.sleep(.001)

    async def test_256_producers_bounded_fifo_one_worker(self):
        seen = []
        active = 0
        maximum = 0
        def job(i):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            if i == 0:
                self.gate.wait(3)
            seen.append(i)
            active -= 1
            return i
        tasks = [self.submit(lambda i=i: job(i)) for i in range(256)]
        await self.until(lambda: self.queue.inflight == 16 and len(self.queue.waiters) == 240)
        self.assertLessEqual(self.pool._work_queue.qsize(), 15)
        self.gate.set()
        self.assertEqual(await asyncio.gather(*tasks), list(range(256)))
        self.assertEqual(seen, list(range(256)))
        self.assertEqual(maximum, 1)
        self.assertEqual(self.queue.maximum, 16)

    async def test_cancellation_storm_does_not_return_capacity_early(self):
        started = threading.Event()
        def block():
            started.set()
            self.gate.wait(3)
        first = self.submit(block)
        await self.until(started.is_set)
        called = []
        old = [self.submit(lambda: called.append('cancelled')) for _ in range(255)]
        await self.until(lambda: self.queue.inflight == 16 and len(self.queue.waiters) == 240)
        for task in old:
            task.cancel()
        await asyncio.gather(*old, return_exceptions=True)
        fresh = [self.submit(lambda: called.append('fresh')) for _ in range(64)]
        await self.until(lambda: len(self.queue.waiters) == 64)
        self.assertEqual(self.queue.inflight, 16)
        self.assertLessEqual(self.pool._work_queue.qsize(), 15)
        self.gate.set()
        await asyncio.gather(first, *fresh)
        self.assertEqual(called, ['fresh'] * 64)

    async def test_cancel_running_keeps_committed_result_and_capacity(self):
        started = threading.Event()
        committed = []
        def write():
            started.set()
            self.gate.wait(3)
            committed.append(1)
        task = self.submit(write)
        await self.until(started.is_set)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(self.queue.inflight, 1)
        self.gate.set()
        await self.until(lambda: self.queue.inflight == 0)
        self.assertEqual(committed, [1])

    async def test_exception_retires_permit(self):
        def fail():
            raise ValueError('fixture')
        with self.assertRaisesRegex(ValueError, 'fixture'):
            await self.submit(fail)
        self.assertEqual(await self.submit(lambda: 42), 42)
        self.assertLessEqual(self.queue.maximum, 16)

    async def test_shutdown_cancels_only_unsubmitted_waiters(self):
        started = threading.Event()
        def block():
            started.set()
            self.gate.wait(3)
            return 'committed'
        first = self.submit(block)
        await self.until(started.is_set)
        rest = [self.submit(lambda: None) for _ in range(32)]
        await self.until(lambda: len(self.queue.waiters) == 17)
        self.queue.close()
        self.gate.set()
        results = await asyncio.gather(first, *rest, return_exceptions=True)
        self.assertEqual(results[0], 'committed')
        self.assertTrue(all(isinstance(e, asyncio.CancelledError) for e in results[16:]))
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            await self.queue.run(lambda: None)

    async def test_application_periodic_and_direct_calls_share_capacity(self):
        from els_server.application import Application
        from els_server.config import ServerConfig
        app = Application(ServerConfig(profile='bootstrap'))
        self.addCleanup(app.close)
        started = threading.Event()
        def block():
            started.set()
            self.gate.wait(3)
        first = asyncio.create_task(app.call(block))
        await self.until(started.is_set)
        def periodic_notifications():
            return []
        members = [SimpleNamespace(periodic_notifications=periodic_notifications)]
        tasks = [asyncio.create_task(app.periodic_batch(members)) for _ in range(31)]
        await self.until(lambda: app.business_queue.inflight == 16)
        self.assertLessEqual(app.executor._work_queue.qsize(), 15)
        self.gate.set()
        await asyncio.gather(first, *tasks)
        self.assertEqual(app.business_queue.maximum, 16)
        self.assertEqual(app.performance.snapshot()['periodic_notifications']['count'], 31)


class SQLiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'owned.sqlite'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE receipts(op TEXT PRIMARY KEY, amount INTEGER)')

    def connect(self, timeout=.03):
        db = sqlite3.connect(self.path, timeout=timeout)
        self.addCleanup(db.close)
        return db

    def reader(self):
        db = self.connect()
        db.execute('BEGIN')
        db.execute('SELECT * FROM receipts').fetchall()
        self.addCleanup(db.rollback)
        return db

    def test_commit_busy_counted_and_entire_transaction_rolls_back(self):
        reader = self.reader()
        db = self.connect()
        sample = {}
        with self.assertRaises(sqlite3.OperationalError):
            with worker_timing(sample), write_transaction(db):
                db.execute("INSERT INTO receipts VALUES ('once',1)")
        self.assertEqual(sample['sql_busy'], 1)
        self.assertEqual(sample['sql_finish_busy'], 1)
        self.assertGreater(sample['sql_finish_wait_ms'], 10)
        self.assertEqual(sample['sql_rollbacks'], 1)
        self.assertFalse(db.in_transaction)
        reader.rollback()
        self.assertEqual(db.execute('SELECT COUNT(*) FROM receipts').fetchone(), (0,))
        with write_transaction(db):
            db.execute("INSERT INTO receipts VALUES ('once',1)")
        self.assertEqual(db.execute('SELECT SUM(amount) FROM receipts').fetchone(), (1,))

    def test_begin_busy_distinct_from_commit(self):
        owner = self.connect()
        owner.execute('BEGIN IMMEDIATE')
        db = self.connect()
        sample = {}
        try:
            with self.assertRaises(sqlite3.OperationalError):
                with worker_timing(sample), write_transaction(db):
                    self.fail('must never enter the writer')
        finally:
            owner.rollback()
        self.assertEqual(sample['sql_busy'], 1)
        self.assertEqual(sample['sql_finish_busy'], 0)
        self.assertNotIn('sql_finish_wait_ms', sample)
        self.assertGreater(sample['sql_begin_wait_ms'], 10)

    def test_successful_commit_wait_visible_without_retry(self):
        ready = threading.Event()
        def reader():
            with closing(sqlite3.connect(self.path)) as db:
                db.execute('BEGIN')
                db.execute('SELECT * FROM receipts').fetchall()
                ready.set()
                time.sleep(.08)
                db.rollback()
        thread = threading.Thread(target=reader)
        thread.start()
        self.addCleanup(thread.join)
        self.assertTrue(ready.wait(2))
        db = self.connect(timeout=1)
        sample = {}
        with worker_timing(sample), write_transaction(db):
            db.execute("INSERT INTO receipts VALUES ('once',1)")
        self.assertGreater(sample['sql_finish_wait_ms'], 10)
        self.assertEqual(sample['sql_busy'], 0)
        self.assertEqual(db.execute('SELECT SUM(amount) FROM receipts').fetchone(), (1,))

    def test_body_failure_retains_original_rollback(self):
        db = self.connect()
        sample = {}
        with self.assertRaisesRegex(ValueError, 'encode'):
            with worker_timing(sample), write_transaction(db):
                db.execute("INSERT INTO receipts VALUES ('once',1)")
                raise ValueError('encode')
        self.assertNotIn('sql_finish_wait_ms', sample)
        self.assertEqual(sample['sql_finish_busy'], 0)
        self.assertEqual(sample['sql_rollbacks'], 1)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM receipts').fetchone(), (0,))

    def test_manual_commit_failure_preserves_callers_rollback_ownership(self):
        reader = self.reader()
        db = self.connect()
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT INTO receipts VALUES ('once',1)")
        sample = {}
        with self.assertRaises(sqlite3.OperationalError), worker_timing(sample):
            commit_write(db)
        self.assertTrue(db.in_transaction)
        self.assertEqual(sample['sql_finish_busy'], 1)
        db.rollback()
        reader.rollback()
        self.assertEqual(db.execute('SELECT COUNT(*) FROM receipts').fetchone(), (0,))

    def test_metrics_include_bounded_finish_window(self):
        metrics = OperationMetrics()
        for i in range(300):
            metrics.record('handle', dict(failed=False, queue_ms=0, handler_ms=0,
                sql_finish_wait_ms=i, sql_finish_busy=1, sql_busy=1))
        row = metrics.snapshot()['handle']
        self.assertEqual(row['window_count'], 256)
        self.assertEqual(row['sql_finish_busy'], 300)
        self.assertGreater(row['sql_finish_wait_ms_p95'], 280)


class GrowthIdentityTests(unittest.TestCase):
    def test_finalizer_uses_current_owned_identity_without_full_dto(self):
        from els_server.domain.selected_2026_growth_runtime import GrowthExtensionFlow
        from els_server.domain import selected_2026_growth_runtime as module
        # The real finalizer's providers are isolated; eligibility is checked
        # at both sides of level99 with identical native entry encoding.
        provider = SimpleNamespace(finalize=lambda s, replies: replies)
        flow = object.__new__(GrowthExtensionFlow)
        flow.participation = SimpleNamespace(enabled=lambda s: True,
            clock=lambda: 1, finalize=provider.finalize)
        flow.growth = SimpleNamespace(_enroll_next=lambda s: None, finalize=provider.finalize)
        flow.pair = provider
        flow.configuration = dict(starts=1, ends=2000000000)
        flow.opened = lambda s, now: True
        flow.last_entries = None
        state = dict(level=98)
        account = SimpleNamespace(uid=1, character_identity=lambda: dict(state),
            character=lambda: self.fail('full character DTO must not load'))
        session = SimpleNamespace(account=account, phase='town_ready')
        for level in (98, 99, 98):
            state['level'] = level
            reply = flow.finalize(session, [])
            self.assertEqual(len(reply), 1)
            row = module.entries.read(reply[0].payload)[678]
            self.assertEqual(row.enabled, level >= 99)
        account.uid = None
        account.character_identity = lambda: self.fail('roster has no selected identity')
        self.assertFalse(module.entries.read(flow.finalize(session, [])[0].payload)[678].enabled)
