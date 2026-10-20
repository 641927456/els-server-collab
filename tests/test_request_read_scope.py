from pathlib import Path
from contextlib import closing
import contextvars
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from els_server.storage.read_scope import committed_reads, role_projection, _current


class CommittedReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.path = Path(self.temp.name) / 'state.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE role(uid PRIMARY KEY,owner,level)')
            db.executemany('INSERT INTO role VALUES (?,?,?)', [(1001,2,1),(1002,2,99)])
        self.account = SimpleNamespace(store=SimpleNamespace(path=self.path),
                                       account_id=2, uid=1001, characters=object())
        self.loads = 0

    def tearDown(self):
        self.assertIsNone(_current.get())
        assert Path(self.temp.name).resolve().parent == ROOT.resolve()
        self.temp.cleanup()

    def load(self):
        self.loads += 1
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute('SELECT uid,level FROM role WHERE uid=? AND owner=?',
                             (self.account.uid,self.account.account_id)).fetchone()
        if row is None:
            raise ValueError('Unknown owned role')
        return dict(uid=row[0],level=row[1],nested={'values':[1,2]})

    def read(self):
        return role_projection(self.account,self.load)

    def test_fresh_scopes_and_mutation_isolation(self):
        with committed_reads():
            first = self.read()
            first['nested']['values'].append(3)
            self.assertEqual(self.read()['nested']['values'],[1,2])
            second = self.read()
            second['nested']['values'].clear()
            self.assertEqual(self.read()['nested']['values'],[1,2])
            self.assertEqual(self.loads,1)
        with committed_reads():
            self.read()
        self.assertEqual(self.loads,2)
        self.read()
        self.assertEqual(self.loads,3)

    def test_committed_update_rollback_and_owner_revocation(self):
        with committed_reads():
            self.assertEqual(self.read()['level'],1)
            with closing(sqlite3.connect(self.path)) as writer, writer:
                writer.execute('UPDATE role SET level=99 WHERE uid=1001')
            self.assertEqual(self.read()['level'],99)
            self.assertEqual(self.loads,2)
            writer = sqlite3.connect(self.path)
            writer.execute('UPDATE role SET level=12 WHERE uid=1001')
            writer.rollback()
            writer.close()
            self.assertEqual(self.read()['level'],99)
            self.assertEqual(self.loads,2)
            with closing(sqlite3.connect(self.path)) as writer, writer:
                writer.execute('UPDATE role SET owner=3 WHERE uid=1001')
            with self.assertRaisesRegex(ValueError,'Unknown owned role'):
                self.read()

    def test_role_switch_and_live_rollback(self):
        with committed_reads():
            self.assertEqual(self.read()['level'],1)
            self.account.uid=1002
            self.assertEqual(self.read()['level'],99)
            self.account.uid=1001
            self.assertEqual(self.read()['level'],1)
            self.assertEqual(self.loads,2)
            with closing(sqlite3.connect(self.path)) as writer, writer:
                writer.execute('UPDATE role SET level=7 WHERE uid=1001')
            self.assertEqual(self.read()['level'],7)

    def test_commit_during_projection_is_not_cached(self):
        def mixed():
            value=self.load()
            with closing(sqlite3.connect(self.path)) as writer, writer:
                writer.execute('UPDATE role SET level=level+1 WHERE uid=1001')
            return value
        with committed_reads():
            self.assertEqual(role_projection(self.account,mixed)['level'],1)
            self.assertEqual(self.read()['level'],2)
            self.assertEqual(self.loads,2)

    def test_nested_scope_exception_closes_observers(self):
        scope=None
        with self.assertRaisesRegex(RuntimeError,'abort'):
            with committed_reads():
                self.read()
                scope=_current.get()
                with committed_reads():
                    self.assertIs(_current.get(),scope)
                    self.read()
                self.assertEqual(self.loads,1)
                raise RuntimeError('abort')
        self.assertEqual(scope.connections,{})
        self.assertEqual(scope.values,{})

    def test_copied_context_does_not_share_sql_connection_between_threads(self):
        results=[]
        with committed_reads():
            self.read()
            context=contextvars.copy_context()
            thread=threading.Thread(target=lambda:context.run(lambda:results.append(self.read()['level'])))
            thread.start();thread.join()
            self.assertEqual(results,[1])
            self.assertEqual(self.loads,2)

    def test_WAL_external_process_commit_invalidates_without_holding_read_tx(self):
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone()[0],'wal')
        with committed_reads():
            self.assertEqual(self.read()['level'],1)
            observer=next(iter(_current.get().connections.values()))
            self.assertFalse(observer.in_transaction)
            code="import sqlite3,sys;from contextlib import closing;\nwith closing(sqlite3.connect(sys.argv[1])) as db,db:db.execute('UPDATE role SET level=77 WHERE uid=1001')"
            subprocess.run([sys.executable,'-B','-c',code,str(self.path)],check=True,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(self.read()['level'],77)
            self.assertEqual(self.loads,2)
            self.assertFalse(observer.in_transaction)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0],0)

    def test_identity_and_full_views_are_distinct_and_both_refresh_on_commit(self):
        def identity():
            value=self.load()
            return dict(uid=value['uid'],level=value['level'])
        with committed_reads():
            self.assertIn('nested',self.read())
            self.assertNotIn('nested',role_projection(self.account,identity,projection='identity'))
            self.assertNotIn('nested',role_projection(self.account,identity,projection='identity'))
            self.assertIn('nested',self.read())
            self.assertEqual(self.loads,2)
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('UPDATE role SET level=42 WHERE uid=1001')
            self.assertEqual(role_projection(self.account,identity,projection='identity')['level'],42)
            self.assertEqual(self.read()['level'],42)
            self.assertEqual(self.loads,4)


if __name__=='__main__':
    unittest.main(verbosity=2)
