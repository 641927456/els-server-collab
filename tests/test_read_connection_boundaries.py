from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from els_server.storage.read_scope import committed_reads,snapshot_connection,_current

ROOT=Path(__file__).resolve().parents[1]

class ReadConnectionBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'scope.sqlite3'
        with closing(sqlite3.connect(self.path))as db,db:db.execute('CREATE TABLE data(v)');db.execute('INSERT INTO data VALUES(1)')

    def test_same_operation_reuses_connection_but_sees_external_commit(self):
        original=sqlite3.connect
        with committed_reads(),patch('els_server.storage.read_scope.sqlite3.connect',wraps=original)as factory:
            with snapshot_connection(self.path)as first:self.assertEqual(first.execute('SELECT v FROM data').fetchone(),(1,))
            with closing(original(self.path))as writer,writer:writer.execute('UPDATE data SET v=2')
            with snapshot_connection(self.path)as second:
                self.assertIs(first,second);self.assertEqual(second.execute('SELECT v FROM data').fetchone(),(2,))
                with self.assertRaises(sqlite3.OperationalError):second.execute('UPDATE data SET v=3')
            self.assertEqual(factory.call_count,1)
        with self.assertRaises(sqlite3.ProgrammingError):first.execute('SELECT 1')

    def test_success_and_failure_never_strand_read_lock_before_writer(self):
        with committed_reads():
            for fail in (False,True):
                try:
                    with snapshot_connection(self.path)as db:
                        db.execute('BEGIN');db.execute('SELECT v FROM data').fetchall()
                        if fail:raise ValueError('own read fixture')
                except ValueError:pass
                self.assertFalse(db.in_transaction)
                with closing(sqlite3.connect(self.path,timeout=0))as writer,writer:
                    writer.execute('BEGIN IMMEDIATE');writer.execute('UPDATE data SET v=v+1')

    def test_nested_reader_preserves_outer_transaction_and_is_disposable(self):
        with committed_reads(),snapshot_connection(self.path)as outer:
            outer.execute('BEGIN');outer.execute('SELECT v FROM data').fetchall()
            with snapshot_connection(self.path)as nested:
                self.assertIsNot(outer,nested);self.assertEqual(nested.execute('SELECT v FROM data').fetchone(),(1,))
            self.assertTrue(outer.in_transaction)
            with self.assertRaises(sqlite3.ProgrammingError):nested.execute('SELECT 1')
        with self.assertRaises(sqlite3.ProgrammingError):outer.execute('SELECT 1')

    def test_generation_change_after_identity_reader_opens_no_observer(self):
        with committed_reads():
            with snapshot_connection(self.path)as before:self.assertEqual(before.execute('SELECT v FROM data').fetchone(),(1,))
            # Windows requires releasing this owned old file handle first.
            before.close();self.path.rename(self.path.with_suffix('.old'))
            with closing(sqlite3.connect(self.path))as writer,writer:
                writer.execute('CREATE TABLE data(v)');writer.execute('INSERT INTO data VALUES(8)')
            from types import SimpleNamespace
            from els_server.storage.read_scope import role_projection
            account=SimpleNamespace(store=SimpleNamespace(path=self.path),characters=object(),account_id=1,uid=1001)
            def load():
                with snapshot_connection(self.path)as db:return db.execute('SELECT v FROM data').fetchone()
            self.assertEqual(role_projection(account,load),(8,))

if __name__=='__main__':unittest.main()
