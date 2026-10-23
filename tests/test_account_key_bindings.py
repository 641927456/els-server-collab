"""Regression: account preferences survive empty rosters and failed writes.

Storage contract only; authenticated Application/TLS and native UI evidence
are recorded separately by the release review.
"""
from pathlib import Path
from contextlib import closing
import sqlite3,struct,tempfile,unittest
from els_server.storage.account_key_bindings import load,save
from els_server.domain.key_bindings import DEFAULT_BINDINGS

class AccountKeyBindingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'game.sqlite3'
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('CREATE TABLE untouched(value TEXT)')
        self.first=struct.pack('>IhhII',1,7,44,0,0)
        self.second=struct.pack('>IhhII',1,7,45,0,0)
    def tearDown(self):self.tmp.cleanup()
    def rows(self):
        with closing(sqlite3.connect(self.path))as db,db:return db.execute('SELECT * FROM account_key_bindings ORDER BY account_id').fetchall()
    def test_empty_roster_cold_restore_and_account_isolation(self):
        self.assertEqual(load(self.path,2),DEFAULT_BINDINGS)
        with closing(sqlite3.connect(self.path))as db,db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='account_key_bindings'").fetchone())
        save(self.path,2,self.first);save(self.path,3,self.second)
        self.assertEqual(load(self.path,2),self.first)
        self.assertEqual(load(self.path,3),self.second)
        self.assertEqual(load(self.path,4),DEFAULT_BINDINGS)
        save(self.path,2,self.first)
        self.assertEqual(self.rows(),[(2,self.first,1),(3,self.second,1)])
    def test_actual_SQL_abort_preserves_previous_preference(self):
        save(self.path,2,self.first);before=self.rows()
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute("CREATE TRIGGER reject_preference BEFORE UPDATE ON account_key_bindings BEGIN SELECT RAISE(ABORT,'test storage failure'); END")
        with self.assertRaises(ValueError):save(self.path,2,self.second)
        self.assertEqual(self.rows(),before)
        self.assertEqual(load(self.path,2),self.first)
    def test_legacy_preferences_require_exact_owner_and_are_preserved(self):
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('CREATE TABLE key_bindings(uid INTEGER PRIMARY KEY,payload BLOB)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER)')
            db.executemany('INSERT INTO character_owners VALUES (?,?)',[(1001,2),(1002,3)])
            db.executemany('INSERT INTO key_bindings VALUES (?,?)',[(1001,self.first),(1002,self.second)])
        self.assertEqual(load(self.path,2),self.first)
        self.assertEqual(load(self.path,3),self.second)
        self.assertEqual(load(self.path,4),DEFAULT_BINDINGS)
        save(self.path,3,self.first)
        with closing(sqlite3.connect(self.path))as db,db:
            self.assertEqual(db.execute('SELECT * FROM key_bindings ORDER BY uid').fetchall(),[(1001,self.first),(1002,self.second)])
        self.assertEqual(load(self.path,2),self.first)
        self.assertEqual(load(self.path,3),self.first)
    def test_invalid_identity_payload_and_corruption_never_become_defaults(self):
        for identity in (0,-1,True,2**63):
            with self.assertRaises(ValueError):save(self.path,identity,self.first)
        with self.assertRaises(ValueError):save(self.path,2,self.first[:-1])
        save(self.path,2,self.first)
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE account_key_bindings SET payload=?',(b'broken',))
        with self.assertRaises(ValueError):load(self.path,2)

if __name__=='__main__':unittest.main()
