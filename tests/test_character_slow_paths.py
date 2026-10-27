import asyncio
from contextlib import closing
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
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.storage.lifecycle import prepare_database
from els_server.storage.read_scope import committed_reads,inventory_projection,role_projection
from els_server.storage.sqlite_timing import write_transaction
from els_server.performance import worker_timing

ROOT=Path(__file__).resolve().parents[1]


class InventoryReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'scope.sqlite3'
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('CREATE TABLE value(v)');db.execute('INSERT INTO value VALUES(1)')
        self.account=SimpleNamespace(account_id=1,uid=1001,characters=object(),store=SimpleNamespace(uid=1001,path=self.path))
        self.inventory=SimpleNamespace(uid=1001,path=self.path);self.loads=0
    def load(self):
        self.loads+=1
        with closing(sqlite3.connect(self.path)) as db:return dict(items=[dict(count=db.execute('SELECT v FROM value').fetchone()[0])])
    def read(self):return inventory_projection(self.account,self.inventory,self.load)
    def test_same_operation_reuses_deep_copy_but_next_operation_reloads(self):
        with committed_reads():
            first=self.read();first['items'][0]['count']=999
            self.assertEqual(self.read()['items'][0]['count'],1);self.assertEqual(self.loads,1)
        with committed_reads():self.read()
        self.assertEqual(self.loads,2)
    def test_external_commit_and_second_boundary_invalidate(self):
        with committed_reads(),patch('els_server.storage.read_scope.time.time',return_value=100):
            self.read()
            with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE value SET v=2')
            self.assertEqual(self.read()['items'][0]['count'],2);self.assertEqual(self.loads,2)
            with patch('els_server.storage.read_scope.time.time',return_value=101):self.read()
            self.assertEqual(self.loads,3)
    def test_live_file_replacement_invalidates_both_role_and_inventory(self):
        with committed_reads():
            self.read();role_projection(self.account,self.load)
            # Windows forbids replacing an open SQLite file. Close this owned
            # observer but retain its cached values to exercise generation change.
            from els_server.storage.read_scope import _current
            _current.get().connections[self.path.resolve()].close()
            self.path.rename(self.path.with_suffix('.old'))
            with closing(sqlite3.connect(self.path)) as db,db:db.execute('CREATE TABLE value(v)');db.execute('INSERT INTO value VALUES(7)')
            self.assertEqual(self.read()['items'][0]['count'],7)
            self.assertEqual(role_projection(self.account,self.load)['items'][0]['count'],7)
    def test_wrong_uid_or_store_never_borrows_cache(self):
        with committed_reads():
            self.read();self.inventory.uid=9999;self.read();self.read()
            self.assertEqual(self.loads,3)
    def test_unscoped_and_foreign_thread_do_not_borrow(self):
        self.read();self.read();self.assertEqual(self.loads,2)
        with committed_reads():
            self.read();thread=threading.Thread(target=self.read);thread.start();thread.join()
            self.assertEqual(self.loads,4)


class WriterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'game.sqlite3';prepare_database(self.path)
        self.base=LocalAccount(LocalState(self.path));self.base.enable_characters()
        self.app=Application(ServerConfig(profile='bootstrap'));self.addCleanup(self.app.close)

    async def test_wait_and_hold_are_separate_and_busy_is_preserved(self):
        entered=threading.Event();release=threading.Event()
        def blocker():
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('BEGIN IMMEDIATE');entered.set();release.wait(3)
        thread=threading.Thread(target=blocker);thread.start();self.assertTrue(await asyncio.to_thread(entered.wait,1))
        samples=[]
        def write():
            sample={}
            try:
                with worker_timing(sample),closing(sqlite3.connect(self.path,timeout=1)) as db,write_transaction(db):db.execute('UPDATE location SET progress=1 WHERE uid=1001')
            finally:samples.append(sample)
        job=asyncio.create_task(self.app.call(write))
        try:
            await asyncio.sleep(.1);release.set();await job
            self.assertGreater(samples[0]['sql_begin_wait_ms'],60)
            self.assertLess(samples[0]['sql_writer_held_ms'],samples[0]['sql_begin_wait_ms'])
        finally:release.set();thread.join();await asyncio.gather(job,return_exceptions=True)
        with closing(sqlite3.connect(self.path)) as blocker:
            blocker.execute('BEGIN IMMEDIATE');sample={}
            with worker_timing(sample),closing(sqlite3.connect(self.path,timeout=.02)) as db:
                with self.assertRaises(sqlite3.OperationalError):
                    with write_transaction(db):pass
            self.assertEqual(sample['sql_busy'],1);self.assertGreater(sample['sql_begin_wait_ms'],10)

    async def test_encoder_failure_rolls_back_all_creation_and_replay_is_exact(self):
        roster=Characters(self.path,2)
        def count():
            with closing(sqlite3.connect(self.path)) as db:return (db.execute('SELECT COUNT(*) FROM characters').fetchone()[0],db.execute('SELECT COUNT(*) FROM inventory_items').fetchone()[0],db.execute('SELECT COUNT(*) FROM character_creation_receipts').fetchone()[0])
        before=count()
        with patch('els_server.protocol.character_messages.create_ack',side_effect=ValueError('owned encoder fixture')):
            with self.assertRaisesRegex(ValueError,'owned encoder fixture'):await self.app.call(roster.create,'SlowFixture',1,'own-create-1')
        self.assertEqual(count(),before)
        first=await self.app.call(roster.create,'SlowFixture',1,'own-create-1');after=count()
        second=await self.app.call(roster.create,'SlowFixture',1,'own-create-1')
        self.assertEqual(first,second);self.assertEqual(count(),after)
        self.assertGreaterEqual(self.app.performance.snapshot()['other']['sql_rollbacks'],1)
        foreign=Characters(self.path,3)
        with self.assertRaisesRegex(ValueError,'another account'):await self.app.call(foreign.create,'SlowFixture',1,'own-create-1')

    async def test_catalog_preparation_is_before_sqlite_writer(self):
        roster=Characters(self.path,2);probed=[]
        def prepare():
            with closing(sqlite3.connect(self.path,timeout=0)) as db:
                db.execute('BEGIN IMMEDIATE');db.rollback();probed.append(True)
        with patch('els_server.storage.characters.prepare_character_catalogs',side_effect=prepare):
            await self.app.call(roster.create,'BeforeLock',1,'own-before-lock')
        self.assertEqual(probed,[True])

    async def test_exact_location_noop_does_not_wait_for_reserved_writer(self):
        state=LocalState(self.path);before=state.load();gate=threading.Event();entered=threading.Event()
        def reserve():
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('BEGIN IMMEDIATE');entered.set();gate.wait(3)
        thread=threading.Thread(target=reserve);thread.start()
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait,1))
            saved=await asyncio.wait_for(self.app.call(state.save,before['map'],before['board'],before['progress'],before['xyz']),.5)
            self.assertEqual(saved,before)
        finally:gate.set();thread.join()

    async def test_changed_location_rechecks_after_external_commit_and_versions_once(self):
        state=LocalState(self.path);gate=threading.Event();entered=threading.Event()
        def change():
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE location SET progress=42,revision=revision+1 WHERE uid=1001')
                entered.set();gate.wait(3)
        thread=threading.Thread(target=change);thread.start();await asyncio.to_thread(entered.wait,1)
        job=asyncio.create_task(self.app.call(state.save,20000,0,1,(0.,0.,0.)))
        try:
            await asyncio.sleep(.08);self.assertFalse(job.done());gate.set();saved=await job
            self.assertEqual(saved['progress'],1);self.assertEqual(saved['revision'],2)
            repeated=await self.app.call(state.save,20000,0,1,(0.,0.,0.));self.assertEqual(repeated,saved)
        finally:gate.set();thread.join();await asyncio.gather(job,return_exceptions=True)

    async def test_for_character_checks_owner_and_finalized_deletion_without_full_projection(self):
        from els_server.domain.roster_account import RosterAccount
        roster=Characters(self.path,2);created=roster.create('OwnedNarrow',1,'own-narrow')
        root=RosterAccount(self.path,2,'qa_narrow')
        with patch.object(root.characters,'get',side_effect=AssertionError('wide identity projection')):
            owned=root.for_character(created['uid']);self.assertEqual(owned.uid,created['uid'])
        foreign=RosterAccount(self.path,3,'qa_other')
        with self.assertRaises(ValueError):foreign.for_character(created['uid'])
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE character_lifecycle SET finalized_at=1 WHERE uid=?',(created['uid'],))
        with self.assertRaises(ValueError):root.for_character(created['uid'])


if __name__=='__main__':unittest.main()
