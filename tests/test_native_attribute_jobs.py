"""SQLite/executor race tests; no player data or game process is used."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch


REFERENCE = Path(__file__).resolve().parents[1]/'references/native-server-attributes-20261027-v1/els_server'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, REFERENCE/path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LEASE = load('candidate_native_attribute_lease', 'storage/native_attribute_lease.py')
JOBS = load('candidate_native_attribute_jobs', 'domain/native_attribute_jobs.py')


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'owned.sqlite3'
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE state(owner INTEGER PRIMARY KEY,value INTEGER)')
        self.db.execute('INSERT INTO state VALUES(1,20)')

    def capture(self, reader=None):
        def read(db, owner, account, *, at):
            self.assertTrue(db.in_transaction)
            return db.execute('SELECT value FROM state WHERE owner=?', (owner,)).fetchone()
        with patch.dict(sys.modules, {'els_server.storage.native_attribute_snapshot':
                                     SimpleNamespace(read_in_transaction=reader or read)}):
            return LEASE.capture(self.path, 1, 2, at=10)

    def test_commit_after_capture_invalidates_same_connection_version(self):
        value, lease = self.capture()
        self.addCleanup(lease.close)
        self.assertEqual(value, (20,))
        self.assertFalse(lease._db.in_transaction)
        self.assertTrue(lease.current())
        # Equivalent new-connection data_version values must not pass as a lease.
        self.db.execute('UPDATE state SET value=21 WHERE owner=1')
        self.assertFalse(lease.current())
        lease.close()
        self.assertFalse(lease.current())

    def test_concurrent_commit_during_capture_rejects_consistent_old_snapshot(self):
        def reader(db, owner, account, *, at):
            first = db.execute('SELECT value FROM state').fetchone()
            self.db.execute('UPDATE state SET value=22')
            self.assertEqual(db.execute('SELECT value FROM state').fetchone(), first)
            return first
        with self.assertRaises(LEASE.SourceChanged):
            self.capture(reader)
        # Reader's rollback did not roll back the independent writer.
        self.assertEqual(self.db.execute('SELECT value FROM state').fetchone(), (22,))

    def test_query_only_rejects_accidental_lazy_writer_and_releases_reader(self):
        def reader(db, owner, account, *, at):
            db.execute('UPDATE state SET value=100')
        with self.assertRaises(sqlite3.OperationalError):
            self.capture(reader)
        self.assertEqual(self.db.execute('SELECT value FROM state').fetchone(), (20,))
        self.db.execute('PRAGMA journal_mode=DELETE')

    def test_validation_from_another_thread_and_file_replacement(self):
        value, lease = self.capture()
        with ThreadPoolExecutor(max_workers=1) as worker:
            self.assertTrue(worker.submit(lease.current).result())
            worker.submit(lease.close).result()
        self.assertFalse(lease.current())
        # The identity boundary is checked independently of the SQL token.
        value, lease = self.capture()
        self.addCleanup(lease.close)
        with patch.object(LEASE, '_identity', return_value=(-1, -1)):
            self.assertFalse(lease.current())

    def test_unrelated_commit_revalidates_only_same_owned_sources(self):
        value, lease = self.capture()
        self.addCleanup(lease.close)
        self.db.execute('INSERT INTO state VALUES(2,40)')
        self.assertFalse(lease.current())
        self.assertTrue(lease.revalidate(at=11))
        self.assertTrue(lease.current())
        self.assertFalse(lease._db.in_transaction)
        self.db.execute('UPDATE state SET value=21 WHERE owner=1')
        self.assertFalse(lease.revalidate(at=12))
        self.assertFalse(lease.current())
        self.assertEqual(value, (20,))

    def test_commit_during_revalidation_retries_without_mixing_epochs(self):
        reads = []
        def reader(db, owner, account, *, at):
            value = db.execute('SELECT value FROM state WHERE owner=?', (owner,)).fetchone()
            reads.append(value)
            if len(reads) == 2:
                self.db.execute('UPDATE state SET value=value+1 WHERE owner=2')
            return value
        self.db.execute('INSERT INTO state VALUES(2,40)')
        value, lease = self.capture(reader)
        self.addCleanup(lease.close)
        self.db.execute('UPDATE state SET value=41 WHERE owner=2')
        self.assertTrue(lease.revalidate(at=11))
        self.assertEqual(len(reads), 3)
        self.assertTrue(lease.current())
        self.assertEqual(self.db.execute('SELECT value FROM state WHERE owner=2').fetchone(), (42,))

    def test_target_commit_during_revalidation_cannot_receive_newer_token(self):
        reads = []
        def reader(db, owner, account, *, at):
            value = db.execute('SELECT value FROM state WHERE owner=?', (owner,)).fetchone()
            reads.append(value)
            if len(reads) == 2:
                self.db.execute('UPDATE state SET value=22 WHERE owner=1')
            return value
        value, lease = self.capture(reader)
        self.addCleanup(lease.close)
        self.db.execute('INSERT INTO state VALUES(2,40)')
        self.assertFalse(lease.revalidate(at=11))
        self.assertEqual(reads, [(20,), (20,), (22,)])
        self.assertFalse(lease.current())

    def test_close_does_not_wait_for_blocked_source_validation(self):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def reader(db, owner, account, *, at):
            value = db.execute('SELECT value FROM state WHERE owner=?', (owner,)).fetchone()
            if at == 11:
                started.set()
                if not release.wait(5):
                    raise TimeoutError('Test failed to release source validation')
            return value
        value, lease = self.capture(reader)
        self.db.execute('INSERT INTO state VALUES(2,40)')
        with ThreadPoolExecutor(max_workers=1) as worker:
            check = worker.submit(lease.revalidate, at=11)
            try:
                self.assertTrue(started.wait(3))
                lease.close()
                self.assertFalse(lease.current())
                self.db.execute('UPDATE state SET value=41 WHERE owner=2')
            finally:
                release.set()
            self.assertFalse(check.result(timeout=3))
        self.db.execute('PRAGMA journal_mode=DELETE')


class FakeLease:
    def __init__(self, valid=True):
        self.valid, self.closed = valid, 0

    def current(self):
        return self.valid and not self.closed

    def close(self):
        self.closed += 1

    def revalidate(self, *, at):
        return self.current()


class JobTests(unittest.IsolatedAsyncioTestCase):
    async def test_source_checks_coalesce_and_replaced_owner_cannot_revive(self):
        jobs = JOBS.AttributeJobs()
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        seen = []
        class SlowLease(FakeLease):
            def revalidate(self, *, at):
                seen.append(threading.current_thread().name)
                started.set()
                if not release.wait(5):
                    raise TimeoutError('Test failed to release source validation')
                return True
        lease = SlowLease()
        try:
            ticket = jobs.refresh('A', 1, lambda: JOBS.Product('old', lease, 100))
            await jobs._pump
            checks = [asyncio.create_task(jobs.revalidate('A', ticket, at=10))for _ in range(20)]
            await asyncio.wait_for(asyncio.to_thread(started.wait, 3), 4)
            self.assertEqual(len(jobs._validations), 1)
            checks[0].cancel()
            with self.assertRaises(asyncio.CancelledError):
                await checks[0]
            next_lease = FakeLease()
            latest = jobs.refresh('A', 2, lambda: JOBS.Product('new', next_lease, 100))
            self.assertEqual(lease.closed, 1)
            release.set()
            self.assertEqual(await asyncio.gather(*checks[1:]), [False]*19)
            await jobs._pump
            self.assertEqual(len(seen), 1)
            self.assertTrue(seen[0].startswith('els-attributes'))
            self.assertTrue(await jobs.revalidate('A', latest, at=11))
            self.assertEqual(jobs.take('A', latest, at=11), 'new')
        finally:
            release.set()
            await jobs.close()

    async def test_source_validation_shutdown_and_expiry_release_every_lease(self):
        jobs = JOBS.AttributeJobs()
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        class SlowLease(FakeLease):
            def revalidate(self, *, at):
                started.set()
                if not release.wait(5):
                    raise TimeoutError('Test failed to release source validation')
                return True
        lease = SlowLease()
        ticket = jobs.refresh('A', 1, lambda: JOBS.Product('old', lease, 20))
        await jobs._pump
        self.assertFalse(await jobs.revalidate('A', ticket, at=20))
        check = asyncio.create_task(jobs.revalidate('A', ticket, at=10))
        await asyncio.wait_for(asyncio.to_thread(started.wait, 3), 4)
        closer = asyncio.create_task(jobs.close())
        await asyncio.sleep(0)
        self.assertEqual(lease.closed, 1)
        release.set()
        self.assertFalse(await check)
        await asyncio.wait_for(closer, 4)
        self.assertEqual(lease.closed, 1)

    async def test_refresh_coalesces_fairly_and_never_uses_account_executor(self):
        jobs = JOBS.AttributeJobs(capacity=2)
        release, started = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        seen, leases, threads = [], [], []
        def build(label, blocked=False):
            def run():
                seen.append(label)
                threads.append(threading.current_thread().name)
                if blocked:
                    started.set()
                    if not release.wait(5):
                        raise TimeoutError('Test failed to release arithmetic')
                lease = FakeLease()
                leases.append(lease)
                return JOBS.Product(label, lease, 100)
            return run
        try:
            old = jobs.refresh('A', 1, build('old-A', True))
            await asyncio.wait_for(asyncio.to_thread(started.wait, 3), 4)
            other = jobs.refresh('B', 2, build('B'))
            for n in range(1000):
                latest = jobs.refresh('A', 3, build(('latest-A', n)))
            self.assertEqual(len(jobs._pending), 2)
            self.assertEqual(len(jobs._entries), 2)
            with self.assertRaises(OverflowError):
                jobs.refresh('C', 4, build('C'))
            # A serialized business worker and event loop remain available
            # while the attribute worker is deliberately held.
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix='els-account') as account:
                result = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(account, lambda: 42), 1)
                self.assertEqual(result, 42)
            self.assertIsNone(jobs.take('A', old, at=10))
            release.set()
            await asyncio.wait_for(jobs._pump, 4)
            self.assertEqual(seen, ['old-A', 'B', ('latest-A', 999)])
            self.assertTrue(all(v.startswith('els-attributes') for v in threads))
            self.assertEqual(leases[0].closed, 1)
            self.assertEqual(jobs.take('B', other, at=10), 'B')
            self.assertIsNone(jobs.take('A', old, at=10))
            self.assertEqual(jobs.take('A', latest, at=10), ('latest-A', 999))
            self.assertIsNone(jobs.take('A', latest, at=10))
            self.assertTrue(all(v.closed == 1 for v in leases))
        finally:
            release.set()
            await jobs.close()

    async def test_expiry_external_commit_and_failure_do_not_send_zero_values(self):
        jobs = JOBS.AttributeJobs()
        try:
            for lease, end, at in ((FakeLease(), 20, 20), (FakeLease(False), None, 10)):
                ticket = jobs.refresh('A', 1, lambda: JOBS.Product('must-not-send', lease, end))
                await jobs._pump
                self.assertIsNone(jobs.take('A', ticket, at=at))
                self.assertEqual(lease.closed, 1)
            def fail():
                raise ValueError('Actual source failed')
            ticket = jobs.refresh('A', 1, fail)
            await jobs._pump
            with self.assertRaisesRegex(ValueError, 'Actual source failed'):
                jobs.take('A', ticket, at=10)
            self.assertEqual(jobs._entries, {})
        finally:
            await jobs.close()

    async def test_release_and_shutdown_discard_inflight_owner_and_close_leases(self):
        jobs = JOBS.AttributeJobs()
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        lease = FakeLease()
        def build():
            started.set()
            release.wait(5)
            return JOBS.Product('closed-owner', lease, None)
        ticket = jobs.refresh('A', 1, build)
        await asyncio.wait_for(asyncio.to_thread(started.wait, 3), 4)
        jobs.discard('A')
        closer = asyncio.create_task(jobs.close())
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(closer, 4)
        self.assertEqual(lease.closed, 1)
        self.assertIsNone(jobs.take('A', ticket, at=10))
        with self.assertRaises(RuntimeError):
            jobs.refresh('A', 1, build)
        self.assertFalse(any(t.name.startswith('els-attributes') and t.is_alive()
                             for t in threading.enumerate()))

    async def test_cancelled_pump_and_cancelled_close_waiter_do_not_leak_source(self):
        jobs = JOBS.AttributeJobs()
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        lease = FakeLease()
        def build():
            started.set()
            release.wait(5)
            return JOBS.Product('abandoned', lease, None)
        jobs.refresh('A', 1, build)
        await asyncio.wait_for(asyncio.to_thread(started.wait, 3), 4)
        jobs._pump.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await jobs._pump
        closer = asyncio.create_task(jobs.close())
        await asyncio.sleep(0)
        closer.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await closer
        release.set()
        await asyncio.wait_for(jobs.close(), 4)
        self.assertEqual(lease.closed, 1)


if __name__ == '__main__':
    unittest.main()
