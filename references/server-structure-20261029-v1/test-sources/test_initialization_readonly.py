"""Actual constructor compatibility, readonly fast paths and locked rechecks."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from hashlib import sha256
from pathlib import Path
from threading import Event
from unittest.mock import patch
import ast
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest

TASK = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['ELS_RUNTIME_ROOT']).resolve()
if RUNTIME not in ((TASK/'runtimes/online').resolve(), (TASK/'runtimes/local').resolve()):
    raise RuntimeError('Use only this task owned runtime')
sys.path.insert(0, str(RUNTIME))
from els_server.storage import local_state, reward_state, inventory_state, initialization_checks as checks

CURRENT = dict(local=(local_state, 'LocalState'), reward=(reward_state, 'RewardState'), inventory=(inventory_state, 'InventoryState'))
BASELINE = {}
SOURCE_SHA = {}
for kind, (module, class_name) in CURRENT.items():
    source = RUNTIME/'els_server/storage'/Path(module.__file__).name
    if Path(module.__file__).resolve() != source:
        raise RuntimeError('Wrong runtime module')
    before = TASK/'initialization-before'/RUNTIME.name/source.name
    spec = importlib.util.spec_from_file_location('initialization_before_'+kind, before)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    BASELINE[kind] = original, class_name
    SOURCE_SHA[source.name] = dict(before=sha256(before.read_bytes()).hexdigest(), candidate=sha256(source.read_bytes()).hexdigest())
SOURCE_SHA['initialization_checks.py'] = dict(candidate=sha256(Path(checks.__file__).read_bytes()).hexdigest())
OBSERVATIONS = {}


def dump(path):
    with closing(sqlite3.connect(path)) as db:
        return db.execute('PRAGMA user_version').fetchone()[0], tuple(db.iterdump())


def copy_database(source, target):
    with closing(sqlite3.connect(source)) as before, closing(sqlite3.connect(target)) as after:
        before.backup(after)


@contextmanager
def writes(module):
    calls = []
    original = module.write_transaction

    @contextmanager
    def recorded(db):
        statements = []
        db.set_trace_callback(statements.append)
        try:
            with original(db) as active:
                calls.append(id(db))
                yield active
        finally:
            db.set_trace_callback(None)
            calls.append(tuple(s for s in statements if s.startswith(('BEGIN', 'COMMIT', 'ROLLBACK'))))

    with patch.object(module, 'write_transaction', recorded):
        yield calls


class InitializationReadonlyTests(unittest.TestCase):
    def setUp(self):
        scratch = TASK/'scratch/initialization-readonly'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix=RUNTIME.name+'-', dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.seed = self.folder/'seed.sqlite'
        for kind in CURRENT:
            module, name = BASELINE[kind]
            getattr(module, name)(self.seed)

    def mutate(self, function):
        with closing(sqlite3.connect(self.seed)) as db, db:
            function(db)

    def run_constructor(self, kind, entry, path, reader=None):
        module, name = entry
        phase = 'construct'
        with writes(module) as calls:
            try:
                instance = getattr(module, name)(path)
                phase = 'read'
                if reader:
                    value = reader(instance)
                else:
                    value = instance.load() if kind == 'local' else instance.balances() if kind == 'reward' else instance.snapshot()
                outcome = ('ok', value)
            except Exception as error:
                outcome = ('error', phase, type(error).__name__, str(error))
        return outcome, len(calls)//2, calls

    def compare(self, kind, *, candidate_writes, reader=None):
        before = self.folder/(kind+'-before.sqlite')
        after = self.folder/(kind+'-after.sqlite')
        copy_database(self.seed, before)
        copy_database(self.seed, after)
        original = self.run_constructor(kind, BASELINE[kind], before, reader)
        candidate = self.run_constructor(kind, CURRENT[kind], after, reader)
        self.assertEqual(candidate[0], original[0])
        self.assertEqual(dump(after), dump(before))
        self.assertEqual(original[1], 1)
        self.assertEqual(candidate[1], candidate_writes)
        return original, candidate, after

    def test_complete_state_has_identical_cold_reads_and_zero_constructor_writes(self):
        before = dump(self.seed)
        for kind in CURRENT:
            with self.subTest(kind=kind):
                old, new, path = self.compare(kind, candidate_writes=0)
                self.assertEqual(dump(path), before)
                self.assertEqual(new[0][0], 'ok')
                OBSERVATIONS[kind] = dict(baseline_writes=old[1], candidate_writes=new[1], logical_dump_equal=True)
        with closing(sqlite3.connect(self.seed)) as db:
            self.assertIsNone(db.execute("SELECT 1 FROM inventory_migrations WHERE name='ice-heater-fashion-native-bag-27-v1'").fetchone())

    def test_first_initialization_of_an_empty_file_keeps_original_schema_and_seeds(self):
        before = self.folder/'empty-before.sqlite'
        after = self.folder/'empty-after.sqlite'
        for kind in CURRENT:
            with self.subTest(kind=kind):
                original = self.run_constructor(kind, BASELINE[kind], before)
                candidate = self.run_constructor(kind, CURRENT[kind], after)
                self.assertEqual(original[0], candidate[0])
                self.assertEqual(candidate[0][0], 'ok')
                self.assertEqual((original[1], candidate[1]), (1,1))
                self.assertEqual(dump(before), dump(after))

    def test_missing_schema_and_seed_rows_use_original_writer(self):
        cases = [('local', 'DROP TABLE ui_layout'), ('reward', 'DROP TABLE reward_title_receipts'),
                 ('inventory', 'DROP TABLE equipment_attributes'),
                 ('local', 'DELETE FROM location'), ('reward', 'DELETE FROM reward_balances'),
                 ('inventory', 'DELETE FROM inventory_sequence')]
        pristine = self.folder/'pristine.sqlite'
        copy_database(self.seed, pristine)
        for kind, sql in cases:
            with self.subTest(sql=sql):
                copy_database(pristine, self.seed)
                self.mutate(lambda db: db.execute(sql))
                self.compare(kind, candidate_writes=1)

    def test_legacy_check_migration_is_seen_by_all_three_constructors(self):
        def legacy(db):
            row = db.execute('SELECT * FROM location').fetchone()
            db.execute('DROP TABLE location')
            db.execute(checks.LOCAL['location'].replace('CHECK(uid>=1001)', 'CHECK(uid=1001)'))
            db.execute('INSERT INTO location VALUES (?,?,?,?,?,?,?,?)', row)
            db.execute('CREATE INDEX legacy_location_town ON location(town)')
        self.mutate(legacy)
        for kind in CURRENT:
            with self.subTest(kind=kind):
                _, _, path = self.compare(kind, candidate_writes=1)
                with closing(sqlite3.connect(path)) as db:
                    self.assertIn('CHECK(uid>=1001)', db.execute("SELECT sql FROM sqlite_master WHERE name='location'").fetchone()[0])
                    self.assertIsNotNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_location_town'").fetchone())
                self.assertEqual(self.run_constructor(kind, CURRENT[kind], path)[1], 0)

    def test_unsupported_shape_falls_back_instead_of_table_exists_shortcut(self):
        self.mutate(lambda db: (db.execute('DROP TABLE ui_layout'), db.execute('CREATE TABLE ui_layout(uid INTEGER PRIMARY KEY,payload BLOB NOT NULL,revision INTEGER NOT NULL)')))
        self.compare('local', candidate_writes=1)

    def test_seed_insert_triggers_keep_original_side_effects(self):
        self.mutate(lambda db: db.execute('CREATE TABLE seed_audit(message TEXT NOT NULL)'))
        for kind, table in (('local','location'), ('reward','reward_balances'), ('inventory','inventory_sequence')):
            with self.subTest(kind=kind):
                self.mutate(lambda db: db.execute("CREATE TRIGGER observe_seed BEFORE INSERT ON "+table+" BEGIN INSERT INTO seed_audit VALUES ('seen'); END"))
                _, _, path = self.compare(kind, candidate_writes=1)
                with closing(sqlite3.connect(path)) as db:
                    self.assertEqual(db.execute('SELECT * FROM seed_audit').fetchall(), [('seen',)])
                self.mutate(lambda db: db.execute('DROP TRIGGER observe_seed'))

    def test_invalid_local_version_location_and_later_layout_errors_are_preserved(self):
        pristine = self.folder/'valid-local.sqlite'
        copy_database(self.seed, pristine)
        for sql in ('PRAGMA user_version=9', 'UPDATE location SET town=99999'):
            with self.subTest(sql=sql):
                copy_database(pristine, self.seed)
                self.mutate(lambda db: db.execute(sql))
                old, new, _ = self.compare('local', candidate_writes=1)
                self.assertEqual(new[0][0:2], ('error', 'construct'))
        copy_database(pristine, self.seed)
        self.mutate(lambda db: db.execute("INSERT INTO ui_layout VALUES (1001,X'00',1)"))
        _, new, _ = self.compare('local', candidate_writes=0, reader=lambda state: state.load_layout())
        self.assertEqual(new[0][0:2], ('error','read'))

    def test_invalid_balance_sequence_and_items_keep_existing_error_timing(self):
        pristine = self.folder/'valid-data.sqlite'
        copy_database(self.seed, pristine)
        self.mutate(lambda db: db.execute("UPDATE reward_balances SET ed='invalid'"))
        _, new, _ = self.compare('reward', candidate_writes=1)
        self.assertEqual(new[0][0:2], ('error','read'))
        copy_database(pristine, self.seed)
        self.mutate(lambda db: db.execute("UPDATE inventory_sequence SET next_uid='invalid'"))
        self.compare('inventory', candidate_writes=1)
        copy_database(pristine, self.seed)
        self.mutate(lambda db: db.execute('INSERT INTO inventory_items VALUES (1001001,1001,999999999,0,1,4,0)'))
        _, new, _ = self.compare('inventory', candidate_writes=0)
        self.assertEqual(new[0][0:2], ('error','read'))
        self.mutate(lambda db: db.execute("DELETE FROM inventory_migrations WHERE name='potion-77000-accessory-to-quick-slot-v1'"))
        _, new, _ = self.compare('inventory', candidate_writes=1)
        self.assertEqual(new[0][0:2], ('error','construct'))

    def add_fashion(self, db, *, full=False):
        template = next(template for template, group in inventory_state.TEMPLATE_BAG_GROUPS.items() if group == 27 and template in inventory_state.VERIFIED_TEMPLATES)
        metadata = inventory_state.VERIFIED_TEMPLATES[template]
        db.execute('INSERT INTO inventory_items VALUES (1001001,1001,?,?,1,7,0)', (template, metadata))
        if full:
            db.executemany('INSERT INTO inventory_items VALUES (?,1001,?,?,1,27,?)', ((1001002+slot, template, metadata, slot) for slot in range(inventory_state.LOCAL_BAG_CAPACITY)))

    def test_fashion_missing_marker_still_discovers_later_old_rows_and_replays(self):
        self.assertEqual(self.run_constructor('inventory', CURRENT['inventory'], self.seed)[1], 0)
        self.mutate(self.add_fashion)
        _, new, path = self.compare('inventory', candidate_writes=1)
        self.assertEqual(new[0][0], 'ok')
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT bag_group FROM inventory_items WHERE uid=1001001').fetchone(), (27,))
            self.assertIsNotNone(db.execute("SELECT audit_json FROM inventory_migrations WHERE name='ice-heater-fashion-native-bag-27-v1'").fetchone())
        before = dump(path)
        self.assertEqual(self.run_constructor('inventory', CURRENT['inventory'], path)[1], 0)
        self.assertEqual(dump(path), before)

    def test_fashion_full_bag_failure_does_not_mark_migration_complete(self):
        self.mutate(lambda db: self.add_fashion(db, full=True))
        before = dump(self.seed)
        _, new, path = self.compare('inventory', candidate_writes=1)
        self.assertEqual(new[0][0:3], ('error','construct','InventoryFull'))
        self.assertEqual(dump(path), before)

    def test_potion_missing_marker_runs_validation_and_records_original_audit(self):
        def old_potion(db):
            db.execute("DELETE FROM inventory_migrations WHERE name='potion-77000-accessory-to-quick-slot-v1'")
            db.execute('INSERT INTO inventory_items VALUES (1001001,1001,77000,2,1,2,0)')
        self.mutate(old_potion)
        _, new, path = self.compare('inventory', candidate_writes=1)
        self.assertEqual(new[0][0], 'ok')
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT bag_group FROM inventory_items').fetchone(), (6,))
        self.assertEqual(self.run_constructor('inventory', CURRENT['inventory'], path)[1], 0)

    def test_complete_constructors_do_not_wait_for_reserved_writer(self):
        original_connect = sqlite3.connect
        def short(*args, **kwargs):
            kwargs['timeout'] = .05
            return original_connect(*args, **kwargs)
        with closing(original_connect(self.seed)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            with patch.object(sqlite3, 'connect', side_effect=short):
                for kind in CURRENT:
                    with self.subTest(kind=kind):
                        result = self.run_constructor(kind, CURRENT[kind], self.seed)
                        self.assertEqual(result[0][0], 'ok')
                        self.assertEqual(result[1], 0)
            writer.rollback()

    def test_probe_ends_before_writer_and_rechecks_same_connection_under_lock(self):
        self.mutate(lambda db: db.execute('DELETE FROM reward_balances WHERE uid=1001'))
        attempted = Event()
        original_write = reward_state.write_transaction
        original_ready = checks.reward_ready
        seen = []
        writer_ids = []

        def ready(db, uid):
            result = original_ready(db, uid)
            seen.append((id(db), db.in_transaction, result))
            return result

        @contextmanager
        def acquiring(db):
            self.assertFalse(db.in_transaction, 'Read snapshot must end before BEGIN IMMEDIATE')
            writer_ids.append(id(db))
            attempted.set()
            with original_write(db) as active:
                yield active

        with closing(sqlite3.connect(self.seed)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            writer.execute('INSERT INTO reward_balances VALUES (1001,123,0,0)')
            with patch.object(checks,'reward_ready',side_effect=ready), patch.object(reward_state,'write_transaction',acquiring), ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(reward_state.RewardState, self.seed)
                if not attempted.wait(5):
                    writer.rollback()
                    self.fail('Constructor did not request writer after incomplete snapshot')
                writer.commit()
                state = future.result(timeout=12)
        self.assertEqual([entry[2] for entry in seen], [False, True])
        self.assertEqual({entry[0] for entry in seen}, set(writer_ids))
        self.assertTrue(all(entry[1] for entry in seen))
        self.assertEqual(state.balances()['ed'], 123)

    def test_checked_schema_definitions_match_actual_writer_ddl(self):
        def ddl(path, class_name=None, function=None):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            if class_name:
                tree = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
                tree = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
            elif function:
                tree = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==function)
            return {checks._definition(node.value) for node in ast.walk(tree) if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value.startswith('CREATE TABLE')}
        for kind, expected in (('local',checks.LOCAL),('reward',checks.REWARD)):
            module, name = CURRENT[kind]
            self.assertEqual(ddl(Path(module.__file__), class_name=name), {checks._definition(s) for s in expected.values()})
        actual = ddl(Path(inventory_state.__file__), function='ensure_inventory')
        actual |= ddl(RUNTIME/'els_server/storage/equipment_attributes.py', function='ensure_attributes')
        self.assertEqual(actual, {checks._definition(s) for s in checks.INVENTORY.values()})


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(InitializationReadonlyTests))
    report = dict(channel=RUNTIME.name, source_sha256=SOURCE_SHA, test_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  tests_run=result.testsRun, success=result.wasSuccessful(), observations=OBSERVATIONS,
                  failures=[dict(test=str(test), traceback=trace) for test,trace in result.failures],
                  errors=[dict(test=str(test), traceback=trace) for test,trace in result.errors],
                  scope='Actual baseline/candidate constructors on owned synthetic G-drive DBs; no services or player DBs')
    (TASK/('initialization-readonly-'+RUNTIME.name+'.json')).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
