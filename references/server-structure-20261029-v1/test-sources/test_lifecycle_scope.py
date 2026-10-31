"""Exercise actual candidate lifecycle/selection functions on owned synthetic DBs.

ELS_RUNTIME_ROOT must name this task's materialized online or local runtime.
No server, player DB, historical test, or static resource is changed by this test.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from threading import Event
from unittest.mock import patch
import json
import os
import sqlite3
import sys
import tempfile
import unittest

TASK = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['ELS_RUNTIME_ROOT']).resolve()
if RUNTIME not in ((TASK / 'runtimes/online').resolve(), (TASK / 'runtimes/local').resolve()):
    raise RuntimeError('Only this task owned materialized runtimes are permitted')
sys.path.insert(0, str(RUNTIME))
from els_server.storage import character_lifecycle as lifecycle
from els_server.storage import character_selection as selection

SOURCE_SHA = {}
for module in (lifecycle, selection):
    relative = Path('els_server/storage') / Path(module.__file__).name
    source = RUNTIME / relative
    candidate = TASK / 'candidate' / RUNTIME.name / relative
    if Path(module.__file__).resolve() != source or source.read_bytes() != candidate.read_bytes():
        raise RuntimeError('The imported runtime must exactly match this channel candidate')
    SOURCE_SHA[str(relative)] = sha256(source.read_bytes()).hexdigest()

NOW = 20 * lifecycle.DAY
OBSERVATIONS = {}


class LifecycleScopeTests(unittest.TestCase):
    def setUp(self):
        scratch = TASK / 'scratch/lifecycle-scope'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix=RUNTIME.name + '-', dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'synthetic.sqlite'

    def seed(self, *, table=True, mixed=False, foreign=0):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY,name_key TEXT UNIQUE NOT NULL,revision INTEGER NOT NULL)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER NOT NULL)')
            db.execute('CREATE TABLE retained_history(uid INTEGER NOT NULL,payload TEXT NOT NULL)')
            ids = tuple(range(1001, 1005)) + tuple(range(20000, 20000 + foreign))
            db.executemany('INSERT INTO characters VALUES (?,?,0)', ((uid, 'synthetic-' + str(uid)) for uid in ids))
            db.executemany('INSERT INTO character_owners VALUES (?,?)', ((uid, 1 if uid < 20000 else 2) for uid in ids))
            db.executemany('INSERT INTO retained_history VALUES (?,?)', ((uid, 'retained-' + str(uid)) for uid in ids))
            if table:
                lifecycle.initialize(db)
                db.executemany('INSERT INTO character_lifecycle(uid,account_id,created_at) VALUES (?,?,1)', ((uid, 1 if uid < 20000 else 2) for uid in ids if uid != 1004))
                if mixed:
                    db.execute('UPDATE character_lifecycle SET requested_at=?,finalize_at=?,restore_at=? WHERE uid=1002', (NOW, NOW + 3*lifecycle.DAY, NOW + lifecycle.DAY))
                    db.execute('UPDATE character_lifecycle SET finalized_at=? WHERE uid=1003', (NOW - 1,))
                    db.execute('UPDATE character_lifecycle SET requested_at=10 WHERE account_id=2')

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return tuple(db.iterdump())

    def state(self, uid):
        with closing(sqlite3.connect(self.path)) as db:
            return lifecycle.states(db, (uid,)).get(uid)

    def reserve_one(self):
        return selection.save(self.path, 1, [1001], [1001, 1002, 1003, 1004])

    def change(self, uid, operation, now=NOW, account=1):
        with patch.object(lifecycle, 'current_time', return_value=now):
            return lifecycle.change(self.path, account, uid, operation)

    def test_missing_lifecycle_and_empty_account_preserve_defaults_without_ddl(self):
        self.seed(table=False)
        before = self.dump()
        self.assertEqual(selection.snapshot(self.path, 1), {'deployed': [1001,1002,1003,1004], 'order': [1001,1002,1003,1004], 'revision': 0})
        self.assertEqual(selection.snapshot(self.path, 99), {'deployed': [], 'order': [], 'revision': 0})
        self.assertEqual(before, self.dump())
        self.reserve_one()
        self.assertEqual(self.change(1004, 'schedule')['restore_at'], NOW + lifecycle.DAY)
        self.assertEqual(self.state(1004)['created_at'], 0)

    def test_empty_owned_set_issues_no_lifecycle_row_select(self):
        self.seed(foreign=1000)
        statements = []
        with closing(sqlite3.connect(self.path)) as db:
            db.set_trace_callback(statements.append)
            self.assertEqual(lifecycle.visible_ids(db, 99), ())
            self.assertEqual(selection._state(db, 99, ()), {'deployed': [], 'order': [], 'revision': 0})
        self.assertFalse(any(s.startswith('SELECT * FROM character_lifecycle') for s in statements))

    def test_foreign_population_scoped_reads_and_mixed_visibility(self):
        self.seed(mixed=True, foreign=10000)
        original = lifecycle.states
        observed = []

        def recording(db, uids=None):
            self.assertIsNotNone(uids, 'Application must not read all accounts lifecycle rows')
            uids = tuple(uids)
            result = original(db, uids)
            self.assertLessEqual(set(uids), {1001,1002,1003,1004})
            observed.append({'uids': list(uids), 'materialized': len(result)})
            return result

        with closing(sqlite3.connect(self.path)) as db:
            all_count = len(original(db))
            owned_count = len(original(db, (1001,1002,1003,1004)))
            foreign_before = tuple(db.execute('SELECT * FROM character_lifecycle WHERE account_id=2'))
        with patch.object(lifecycle, 'states', side_effect=recording):
            expected = {'deployed': [1001,0,1004], 'order': [1001,1002,1004], 'revision': 0}
            self.assertEqual(selection.snapshot(self.path, 1), expected)
            self.assertEqual(selection.save(self.path, 1, expected['deployed'], expected['order']), expected)
            self.change(1002, 'restore', NOW + lifecycle.DAY)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM character_lifecycle WHERE account_id=2')), foreign_before)
            self.assertEqual(lifecycle.visible_ids(db, 1), (1001,1002,1004))
        self.assertEqual((all_count, owned_count), (10003, 3))
        OBSERVATIONS['foreign_population'] = {'foreign_rows': 10000, 'baseline_materialized': all_count, 'scoped_materialized': owned_count, 'actual_function_calls': observed}

    def test_selection_order_empty_slots_save_replay_and_cold_read(self):
        self.seed()
        desired = {'deployed': [0,1004,0,1001], 'order': [1004,1002,1001,1003], 'revision': 1}
        self.assertEqual(selection.save(self.path, 1, desired['deployed'], desired['order']), desired)
        before = self.dump()
        self.assertEqual(selection.save(self.path, 1, desired['deployed'], desired['order']), desired)
        self.assertEqual(selection.snapshot(self.path, 1), desired)
        self.assertEqual(self.dump(), before)

    def test_invalid_selection_pending_foreign_and_duplicate_are_atomic(self):
        self.seed(mixed=True, foreign=1)
        before = self.dump()
        cases = [([1002], [1001,1002,1004], 'Pending deletion'),
                 ([20000], [1001,1002,1004], 'Unowned deployment'),
                 ([1001,1001], [1001,1002,1004], 'Duplicate deployment'),
                 ([1001], [1001,1002,20000], 'Incomplete character order')]
        for deployed, order, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                selection.save(self.path, 1, deployed, order)
            self.assertEqual(self.dump(), before)

    def test_schedule_restore_wait_cooldown_and_replays(self):
        self.seed()
        self.reserve_one()
        first = self.change(1002, 'schedule')
        self.assertEqual(first, {'uid':1002, 'operation':'schedule', 'until':NOW+3*lifecycle.DAY, 'restore_at':NOW+lifecycle.DAY})
        before = self.dump()
        self.assertEqual(self.change(1002, 'schedule', NOW+1), first)
        self.assertEqual(self.dump(), before)
        with self.assertRaises(lifecycle.LifecycleError) as caught:
            self.change(1002, 'restore', NOW+1)
        self.assertEqual((caught.exception.result, caught.exception.until), (0x3d4, NOW+lifecycle.DAY))
        self.assertEqual(self.dump(), before)
        restored = self.change(1002, 'restore', NOW+lifecycle.DAY)
        self.assertEqual(restored, {'uid':1002, 'operation':'restore', 'until':NOW+2*lifecycle.DAY})
        before = self.dump()
        self.assertEqual(self.change(1002, 'restore', NOW+lifecycle.DAY+1), restored)
        self.assertEqual(self.dump(), before)
        with self.assertRaises(lifecycle.LifecycleError) as caught:
            self.change(1002, 'schedule', NOW+lifecycle.DAY+1)
        self.assertEqual((caught.exception.result, caught.exception.until), (0x3d4, NOW+2*lifecycle.DAY))
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.change(1002, 'schedule', NOW+2*lifecycle.DAY)['until'], NOW+5*lifecycle.DAY)

    def test_finalization_tombstone_retained_history_selection_and_replay(self):
        self.seed(foreign=2)
        saved = self.reserve_one()
        self.change(1002, 'schedule')
        before = self.dump()
        with self.assertRaises(lifecycle.LifecycleError) as caught:
            self.change(1002, 'finalize', NOW+2*lifecycle.DAY)
        self.assertEqual((caught.exception.result, caught.exception.until), (0x3d4, NOW+3*lifecycle.DAY))
        self.assertEqual(self.dump(), before)
        final = self.change(1002, 'finalize', NOW+3*lifecycle.DAY)
        self.assertEqual(selection.snapshot(self.path, 1), {'deployed':[1001], 'order':[1001,1003,1004], 'revision':saved['revision']+1})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT name_key,revision FROM characters WHERE uid=1002').fetchone(), (':deleted:1002',1))
            self.assertEqual(db.execute('SELECT payload FROM retained_history WHERE uid=1002').fetchone(), ('retained-1002',))
            self.assertEqual(db.execute('SELECT account_id FROM character_owners WHERE uid=1002').fetchone(), (1,))
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone(), ('ok',))
        before = self.dump()
        self.assertEqual(self.change(1002, 'finalize', NOW+4*lifecycle.DAY), final)
        for operation in ('schedule', 'restore'):
            with self.assertRaisesRegex(lifecycle.LifecycleError, 'already deleted'):
                self.change(1002, operation, NOW+4*lifecycle.DAY)
        self.assertEqual(self.dump(), before)

    def test_cross_owner_missing_uid_deployed_and_creation_protection(self):
        self.seed()
        before = self.dump()
        for operation in ('schedule','restore','finalize'):
            for account, uid in ((2,1002), (1,9999)):
                with self.subTest(operation=operation, account=account, uid=uid), self.assertRaisesRegex(lifecycle.LifecycleError, 'Character ownership'):
                    self.change(uid, operation, account=account)
                self.assertEqual(self.dump(), before)
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'Deployed character'):
            self.change(1002, 'schedule')
        self.reserve_one()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE character_lifecycle SET created_at=? WHERE uid=1002', (NOW-1,))
        before = self.dump()
        with self.assertRaises(lifecycle.LifecycleError) as caught:
            self.change(1002, 'schedule')
        self.assertEqual((caught.exception.result, caught.exception.until), (0x9b6, NOW-1+3*lifecycle.DAY))
        self.assertEqual(self.dump(), before)

    def test_finalization_failure_rolls_back_earlier_lifecycle_update(self):
        self.seed()
        self.reserve_one()
        self.change(1002, 'schedule')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TRIGGER reject_tombstone BEFORE UPDATE OF name_key ON characters WHEN NEW.uid=1002 BEGIN SELECT RAISE(ABORT,'injected tombstone failure'); END")
        before = self.dump()
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'injected tombstone failure'):
            self.change(1002, 'finalize', NOW+3*lifecycle.DAY)
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.state(1002)['finalized_at'], 0)

    def test_selection_write_failure_preserves_previous_preferences(self):
        self.seed()
        self.reserve_one()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TRIGGER reject_selection BEFORE UPDATE ON character_selection_preferences BEGIN SELECT RAISE(ABORT,'injected selection failure'); END")
        before = self.dump()
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'injected selection failure'):
            selection.save(self.path, 1, [1002], [1004,1003,1002,1001])
        self.assertEqual(self.dump(), before)

    def after_writer_commit(self, mutation, operation):
        started = Event()
        real_connect = sqlite3.connect

        class ObservedConnection(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if sql == 'BEGIN IMMEDIATE':
                    started.set()
                return super().execute(sql, *args, **kwargs)

        def candidate_connection(path, *args, **kwargs):
            self.assertEqual(Path(path).resolve(), self.path.resolve())
            return real_connect(path, *args, factory=ObservedConnection, **kwargs)

        with closing(real_connect(self.path, timeout=10)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            writer.execute(mutation)
            with patch.object(sqlite3, 'connect', side_effect=candidate_connection), ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(operation)
                if not started.wait(5):
                    writer.rollback()
                    self.fail('Candidate did not reach its existing BEGIN IMMEDIATE')
                writer.commit()
                with self.assertRaises(ValueError) as caught:
                    future.result(timeout=12)
                return str(caught.exception)

    def test_waiting_selection_rechecks_newly_pending_state_after_write_lock(self):
        self.seed()
        self.reserve_one()
        message = self.after_writer_commit('UPDATE character_lifecycle SET requested_at=1 WHERE uid=1002', lambda: selection.save(self.path, 1, [1002], [1001,1002,1003,1004]))
        self.assertIn('Pending deletion', message)
        self.assertEqual(selection.snapshot(self.path, 1)['deployed'], [1001])
        self.assertEqual(self.state(1002)['requested_at'], 1)

    def test_waiting_lifecycle_rechecks_owner_after_write_lock(self):
        self.seed()
        self.reserve_one()
        message = self.after_writer_commit('UPDATE character_owners SET account_id=2 WHERE uid=1002', lambda: self.change(1002, 'schedule'))
        self.assertIn('Character ownership', message)
        self.assertEqual(self.state(1002)['requested_at'], 0)
        self.assertEqual(selection.snapshot(self.path, 1)['order'], [1001,1003,1004])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LifecycleScopeTests))
    report = {'channel': RUNTIME.name, 'runtime': str(RUNTIME), 'source_sha256': SOURCE_SHA,
              'test_sha256': sha256(Path(__file__).read_bytes()).hexdigest(), 'tests_run': result.testsRun,
              'failures': [{'test': str(t), 'traceback': tb} for t,tb in result.failures],
              'errors': [{'test': str(t), 'traceback': tb} for t,tb in result.errors],
              'successful': result.wasSuccessful(), 'observations': OBSERVATIONS,
              'boundaries': ['Synthetic task-owned SQLite files only; all deleted after tests',
                             'Actual candidate functions and real deletion guards imported from materialized runtime',
                             'No service, live database, game, deployment, Git merge, or native GUI test']}
    destination = TASK / ('scope-lifecycle-results-' + RUNTIME.name + '.json')
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
