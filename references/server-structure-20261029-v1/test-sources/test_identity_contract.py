"""Current identity contract through real candidate readers and an owned DB.

Set ELS_RUNTIME_ROOT to one explicitly materialized channel. The incomplete and
wrong-owner cases corrupt only the operation-local cached value as fault input;
all direct readers, source identity guards, and SQL ownership checks stay real.
"""
from contextlib import closing
from pathlib import Path
from types import MethodType
from unittest.mock import patch
import os
import sqlite3
import sys
import tempfile
import unittest

TASK = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['ELS_RUNTIME_ROOT']).resolve()
if not RUNTIME.is_relative_to(TASK / 'runtimes'):
    raise RuntimeError('Use this task owned materialized runtime, never a live runtime')
sys.path.insert(0, str(RUNTIME))

from els_server.domain.local_session import LocalAccount
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.read_scope import committed_reads, role_projection, _current
import els_server.storage.read_scope as read_scope

if Path(read_scope.__file__).resolve() != RUNTIME / 'els_server/storage/read_scope.py':
    raise RuntimeError('Unexpected imported candidate source')


class IdentityContractTests(unittest.TestCase):
    def setUp(self):
        scratch = TASK / 'scratch/identity-contract'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix=RUNTIME.name + '-', dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'owned.sqlite'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.account.enable_inventory()
        self.direct = self.account.character_identity()
        self.assertEqual(self.direct['account_id'], 1)

    def cached_full(self):
        self.account.character()
        scope = _current.get()
        key = (self.path.resolve(), (self.account.account_id, self.account.uid,
                                    id(self.account.characters), 'full'))
        saved = scope.values[key]
        self.assertEqual(saved[2], self.account._character_projection)
        return scope, key, saved

    def replace_cached_full_value(self, update):
        scope, key, saved = self.cached_full()
        value = dict(saved[1])
        update(value)
        scope.values[key] = (saved[0], value, saved[2])

    def assert_direct_fallback(self, expected=None):
        # Wrap the connection seam, not any exact-reader identity check.
        with patch.object(read_scope, 'snapshot_connection', wraps=read_scope.snapshot_connection) as connect:
            result = self.account.character_identity()
        self.assertGreater(connect.call_count, 0)
        self.assertEqual(result, self.direct if expected is None else expected)

    def test_direct_and_full_derived_identity_have_exact_same_contract(self):
        with committed_reads():
            self.account.character()
            with patch.object(read_scope, 'snapshot_connection', side_effect=AssertionError('derived identity must not reread SQL')):
                self.assertEqual(self.account.character_identity(), self.direct)
        self.assertEqual(set(self.direct), {'uid', 'name', 'unit_type', 'unit_class', 'level',
                                           'transcendence', 'master', 'revision', 'account_id'})

    def test_missing_account_id_in_full_source_falls_back_to_direct_reader(self):
        with committed_reads():
            self.replace_cached_full_value(lambda row: row.pop('account_id'))
            self.assert_direct_fallback()

    def test_wrong_owner_in_full_source_falls_back_to_direct_reader(self):
        with committed_reads():
            self.replace_cached_full_value(lambda row: row.update(account_id=2, level=77))
            self.assert_direct_fallback()

    def test_identity_and_full_results_are_detached_from_cached_values(self):
        with committed_reads():
            full = self.account.character()
            full.update(account_id=2, level=77)
            first = self.account.character_identity()
            self.assertEqual(first, self.direct)
            first.update(account_id=3, level=88)
            self.assertEqual(self.account.character_identity(), self.direct)
            self.assertEqual(self.account.character()['account_id'], 1)
            self.assertEqual(self.account.character()['level'], self.direct['level'])

    def test_external_commit_invalidates_the_derived_identity(self):
        with committed_reads():
            self.account.character()
            self.assertEqual(self.account.character_identity(), self.direct)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('UPDATE characters SET level=9, revision=revision+1 WHERE uid=1001')
            expected = dict(self.direct, level=9, revision=self.direct['revision'] + 1)
            self.assert_direct_fallback(expected)

    def test_external_owner_revocation_is_not_hidden_by_full_source(self):
        with committed_reads():
            self.account.character()
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('UPDATE character_owners SET account_id=2 WHERE uid=1001')
            with self.assertRaisesRegex(ValueError, 'Unknown character'):
                self.account.character_identity()

    def test_another_account_key_cannot_borrow_a_cached_full_source(self):
        with committed_reads():
            self.account.character()
            self.account.account_id = 2
            self.account.characters.account_id = 2
            with self.assertRaisesRegex(ValueError, 'Unknown character'):
                self.account.character_identity()

    def test_untrusted_callback_cannot_seed_a_derived_identity(self):
        full = self.account.character()
        with committed_reads():
            role_projection(self.account, lambda: dict(full, level=77))
            self.assert_direct_fallback()

    def test_custom_account_full_reader_cannot_seed_a_derived_identity(self):
        full = self.account.character()
        self.account._character_projection = MethodType(lambda actor: dict(full, level=77), self.account)
        with committed_reads():
            self.account.character()
            self.assert_direct_fallback()

    def test_custom_character_get_cannot_seed_a_derived_identity(self):
        full = self.account.character()
        self.account.characters.get = lambda uid: dict(full, level=77)
        with committed_reads():
            self.account.character()
            self.assert_direct_fallback()

    def test_custom_character_project_cannot_seed_a_derived_identity(self):
        full = self.account.character()
        self.account.characters._project = lambda uid=None: [dict(full, level=77)]
        with committed_reads():
            self.account.character()
            self.assert_direct_fallback()

    def test_custom_character_row_cannot_seed_a_derived_identity(self):
        original = self.account.characters._row
        self.account.characters._row = lambda row: dict(original(row), level=77)
        with committed_reads():
            self.account.character()
            self.assert_direct_fallback(dict(self.direct, level=77))

    def test_custom_identity_reader_preserves_its_existing_result(self):
        self.account.characters.identity = lambda uid: dict(uid=uid, custom=True, account_id=999)
        with committed_reads():
            self.account.character()
            self.assertEqual(self.account.character_identity(), dict(uid=self.account.uid, custom=True, account_id=999))


if __name__ == '__main__':
    unittest.main(verbosity=2)
