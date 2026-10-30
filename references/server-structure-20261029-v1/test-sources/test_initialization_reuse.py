"""Measure real initialization transactions and preserve owned-account behavior."""
from contextlib import closing, contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['ELS_RUNTIME_ROOT']).resolve()
BASELINE = os.environ.get('ELS_INITIALIZATION_BASELINE') == '1'
if RUNTIME not in ((TASK / 'runtimes/online').resolve(), (TASK / 'runtimes/local').resolve()):
    raise RuntimeError('Only this task owned runtimes are permitted')
sys.path.insert(0, str(RUNTIME))
from els_server import application
from els_server.domain import local_session, roster_account
from els_server.storage import characters, role_loadout, master_presets
from els_server.application import Application
from els_server.domain.local_session import LocalAccount
from els_server.domain.roster_account import RosterAccount
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState

PREVIOUS = json.loads((TASK / 'initialization-reuse-before-sha.json').read_text())
SOURCE_SHA = {}
for module, relative in ((application, 'application.py'), (local_session, 'domain/local_session.py'),
                         (roster_account, 'domain/roster_account.py')):
    source = RUNTIME / 'els_server' / relative
    expected = (Path(PREVIOUS[RUNTIME.name][relative]['baseline']) if BASELINE
                else TASK / 'candidate' / RUNTIME.name / 'els_server' / relative)
    if Path(module.__file__).resolve() != source or source.read_bytes() != expected.read_bytes():
        raise RuntimeError('Runtime must exactly match the selected baseline or candidate')
    SOURCE_SHA[relative] = sha256(source.read_bytes()).hexdigest()

OBSERVATIONS = {}


def database_digest(path):
    with closing(sqlite3.connect(path)) as db:
        return sha256('\n'.join(db.iterdump()).encode()).hexdigest()


@contextmanager
def count_initialization():
    instances = []
    transactions = []
    original_init = Characters.__init__
    original_transaction = characters.write_transaction

    def initialize(instance, *args, **kwargs):
        original_init(instance, *args, **kwargs)
        instances.append(instance)

    @contextmanager
    def transaction(db):
        statements = []
        db.set_trace_callback(statements.append)
        try:
            with original_transaction(db) as active:
                yield active
        finally:
            db.set_trace_callback(None)
            transactions.append([s.upper() for s in statements if s.upper().startswith(('BEGIN', 'COMMIT', 'ROLLBACK'))])

    with patch.object(Characters, '__init__', initialize), patch.object(characters, 'write_transaction', transaction):
        yield instances, transactions


class InitializationReuseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        scratch = TASK / 'scratch/initialization-reuse'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix=RUNTIME.name + '-', dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'owned.sqlite3'

    def app(self):
        config = SimpleNamespace(mode='friends', state_file=self.path, session_options=lambda: {})
        app = Application(config)
        self.addCleanup(app.close)
        return app

    async def measure_session(self, account_id):
        # A known legacy local role is owned only by account 1; account 2 is empty.
        Characters(self.path, 1)
        app = self.app()
        identity = dict(id=account_id, name='synthetic')
        with count_initialization() as (instances, transactions):
            session = await app.session(identity=identity)
            repeated = await app.session(identity=identity)
        expected = 2 if BASELINE else 1
        self.assertEqual(len(instances), expected)
        self.assertEqual(transactions, [['BEGIN IMMEDIATE', 'COMMIT']] * expected)
        account = session.account
        self.assertIs(account, repeated.account)
        self.assertIs(account, app.accounts[account_id])
        self.assertIs(account.characters, instances[-1])
        self.assertEqual((account.characters.path, account.characters.account_id), (self.path, account_id))
        if account_id == 1:
            self.assertEqual((account.uid, account.store.uid), (1001, 1001))
            self.assertEqual(account.character_identity()['account_id'], 1)
            self.assertIs(account.character_accounts[1001], account)
            self.assertIsNotNone(account.inventory_store)
            self.assertIsNotNone(account.reward_store)
            self.assertEqual(account.initial_loadout_repair, dict(repaired=[], deferred=[]))
            self.assertEqual(account.master_preset_repair, [])
        else:
            self.assertIsNone(account.uid)
            self.assertIsNone(account.store)
            self.assertEqual(account.characters.list(), [])
            self.assertIsNone(account.inventory_store)
            self.assertIsNone(account.reward_store)
            with closing(sqlite3.connect(self.path)) as db:
                names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertFalse(names & {'location', 'reward_balances', 'inventory_items'})
                self.assertEqual(db.execute('SELECT uid,account_id FROM character_owners').fetchall(), [(1001, 1)])
        observed = dict(constructors=len(instances), transactions=transactions,
                        database_sha256=database_digest(self.path), roster_uids=[r['uid'] for r in account.characters.list()],
                        account_id=account_id, uid=account.uid)
        branch = 'occupied' if account_id == 1 else 'empty'
        OBSERVATIONS[branch] = observed
        if not BASELINE:
            baseline = json.loads((TASK / ('initialization-baseline-' + RUNTIME.name + '.json')).read_text())['branches'][branch]
            self.assertEqual(observed['constructors'], baseline['constructors'] - 1)
            self.assertEqual(observed['database_sha256'], baseline['database_sha256'])
            self.assertEqual(observed['roster_uids'], baseline['roster_uids'])
        # A new application must read the same persisted identity and state.
        cold = await self.app().session(identity=identity)
        self.assertEqual(cold.account.uid, account.uid)
        self.assertEqual(cold.account.characters.list(), account.characters.list())
        self.assertEqual(database_digest(self.path), observed['database_sha256'])

    async def test_occupied_session_removes_exactly_one_constructor_and_transaction(self):
        await self.measure_session(1)

    async def test_empty_session_removes_exactly_one_constructor_without_dummy_save(self):
        await self.measure_session(2)

    @unittest.skipIf(BASELINE, 'New optional reuse contract')
    async def test_reuse_rejects_foreign_path_account_and_non_exact_store_before_writes(self):
        same = Characters(self.path, 1)
        account = LocalAccount(LocalState(self.path), 1, 'synthetic')
        other_path = self.path.with_name('foreign.sqlite3')
        foreign_path = Characters(other_path, 1)
        foreign_account = Characters(self.path, 2)
        subclass = type('DerivedCharacters', (Characters,), {})(self.path, 1)
        invalid = (foreign_path, foreign_account, subclass, object(), False,
                   SimpleNamespace(path=self.path, account_id=1))
        before = database_digest(self.path)
        foreign_before = database_digest(other_path)
        for existing in invalid:
            with self.subTest(existing=type(existing).__name__):
                with self.assertRaises(ValueError):
                    account.enable_characters(characters=existing)
                with self.assertRaises(ValueError):
                    RosterAccount(self.path, 1, 'synthetic', characters=existing)
                self.assertIsNone(account.characters)
                self.assertIsNone(account.inventory_store)
                self.assertIsNone(account.reward_store)
                self.assertEqual(database_digest(self.path), before)
                self.assertEqual(database_digest(other_path), foreign_before)
        same.account_id = True
        with self.assertRaises(ValueError):
            account.enable_characters(characters=same)
        same.account_id = 1
        account.account_id = True
        with self.assertRaises(ValueError):
            account.enable_characters(characters=same)
        for invalid_id in (0, -1, 2**63, None, 1., '1'):
            same.account_id = account.account_id = invalid_id
            with self.assertRaises(ValueError):
                account.enable_characters(characters=same)
            with self.assertRaises(ValueError):
                RosterAccount(self.path, invalid_id, 'synthetic', characters=same)
        self.assertEqual(database_digest(self.path), before)

    @unittest.skipIf(BASELINE, 'New optional reuse contract')
    async def test_public_no_argument_enable_retains_rebuild_repairs_and_return_value(self):
        Characters(self.path, 1)
        account = LocalAccount(LocalState(self.path), 1, 'synthetic')
        with count_initialization() as (instances, transactions), \
                patch.object(role_loadout, 'repair_created_loadouts', wraps=role_loadout.repair_created_loadouts) as loadouts, \
                patch.object(master_presets, 'repair', wraps=master_presets.repair) as masters:
            self.assertIsNone(account.enable_characters())
            first = account.characters
            inventory = account.inventory_store
            before = database_digest(self.path)
            self.assertIsNone(account.enable_characters())
            self.assertIsNot(account.characters, first)
            self.assertIs(account.inventory_store, inventory)
            self.assertEqual(len(instances), 2)
            self.assertEqual(len(transactions), 2)
            self.assertEqual((loadouts.call_count, masters.call_count), (2, 2))
            self.assertEqual(database_digest(self.path), before)
            self.assertIsNone(account.enable_characters(characters=account.characters))
            self.assertEqual(len(instances), 2)
            self.assertEqual((loadouts.call_count, masters.call_count), (3, 3))
            self.assertEqual(database_digest(self.path), before)
        # The RosterAccount no-argument constructor and return contract also remain.
        with count_initialization() as (instances, transactions):
            roster = RosterAccount(self.path, 2, 'synthetic')
            self.assertIs(roster.enable_characters(), roster.characters)
            self.assertIs(roster.enable_characters(), roster.characters)
            self.assertEqual((len(instances), len(transactions)), (1, 1))

    @unittest.skipIf(BASELINE, 'New optional reuse contract')
    async def test_empty_roster_later_creation_selection_and_cold_read_keep_ownership(self):
        # Application.start normally prepares the shared gameplay schema using
        # the existing local role before any empty authenticated roster connects.
        seed = LocalAccount(LocalState(self.path), 1, 'synthetic-local')
        seed.enable_characters()
        roster = Characters(self.path, 2)
        account = RosterAccount(self.path, 2, 'synthetic', characters=roster)
        created = roster.create('ReuseRole', 1, 'owned-initialization-reuse')
        with count_initialization() as (instances, transactions):
            selected = account.for_character(created['uid'])
            self.assertIs(selected, account.for_character(created['uid']))
            self.assertEqual((len(instances), len(transactions)), (0, 0))
        self.assertIs(selected.characters, roster)
        self.assertIs(selected.root, account)
        self.assertEqual(selected.character_identity()['account_id'], 2)
        self.assertEqual(selected.store.uid, created['uid'])
        self.assertIsNotNone(selected.inventory_store)
        with self.assertRaises(ValueError):
            account.for_character(1001)
        selected.store.save(20000, 2, 30, (1., 2., 3.))
        cold = RosterAccount(self.path, 2, 'synthetic').for_character(created['uid'])
        self.assertEqual(cold.store.load(), selected.store.load())
        self.assertEqual(cold.character_identity(), selected.character_identity())
        self.assertEqual(roster.create('ReuseRole', 1, 'owned-initialization-reuse')['uid'], created['uid'])

    @unittest.skipIf(BASELINE, 'New optional reuse contract')
    async def test_existing_root_later_character_uses_shared_roster_and_keeps_saved_state(self):
        Characters(self.path, 1)
        account = (await self.app().session(identity=dict(id=1, name='synthetic'))).account
        roster = account.characters
        created = roster.create('SecondRole', 1, 'owned-second-role')
        with count_initialization() as (instances, transactions):
            selected = account.for_character(created['uid'])
            self.assertIs(selected, account.for_character(created['uid']))
            self.assertEqual((len(instances), len(transactions)), (0, 0))
        self.assertIs(selected.characters, roster)
        self.assertIs(selected.root, account)
        self.assertEqual(account.uid, 1001)
        self.assertEqual(selected.character_identity()['account_id'], 1)
        selected.store.save(20000, 3, 45, (4., 5., 6.))
        cold_root = (await self.app().session(identity=dict(id=1, name='synthetic'))).account
        cold = cold_root.for_character(created['uid'])
        self.assertEqual(cold.store.load(), selected.store.load())
        self.assertEqual(cold.character_identity(), selected.character_identity())

    @classmethod
    def tearDownClass(cls):
        output = TASK / ('initialization-' + ('baseline-' if BASELINE else 'candidate-') + RUNTIME.name + '.json')
        output.write_text(json.dumps(dict(runtime=str(RUNTIME), baseline=BASELINE,
                                         source_sha256=SOURCE_SHA, branches=OBSERVATIONS), indent=2) + '\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
