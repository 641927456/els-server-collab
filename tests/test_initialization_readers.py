from contextlib import closing
from dataclasses import FrozenInstanceError
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from els_server.domain import boosting_2026 as boost
from els_server.domain import resonance_2026_allocations as resonance
from els_server.domain.resonance_allocation_flow import definitions
from els_server.domain.boosting_2026_quests import BoostingQuestBinding
from els_server.storage.boosting_2026_participation import BoostingParticipation
from els_server.performance import worker_timing
from els_server.storage import ariel_cash, fishing_attempt

ROOT=Path(__file__).resolve().parents[1]
RAW=(ROOT/'els_server/data/selected2026/growth-growth.json').read_bytes()


class ImmutableDefinitionTests(unittest.TestCase):
    def test_boost_is_cached_frozen_and_tamper_still_rejected(self):
        boost._original_definition.cache_clear()
        first=boost.BoostingDefinition.from_original(RAW)
        self.assertIs(first,boost.BoostingDefinition.from_original(RAW))
        self.assertEqual(boost._original_definition.cache_info().hits,1)
        with self.assertRaises(FrozenInstanceError):first.code=1
        with self.assertRaises(FrozenInstanceError):first.tasks[0].quest_id=1
        with self.assertRaises(ValueError):boost.BoostingDefinition.from_original(RAW+b' ')

    def test_mutable_boost_input_retains_original_rejection(self):
        with self.assertRaises(ValueError):boost.BoostingDefinition.from_original(bytearray(RAW))
        with self.assertRaises(ValueError):boost.BoostingDefinition.from_original('bad')

    def test_stat_rules_frozen_cached_but_mutable_inputs_never_cached(self):
        _,raw=definitions()
        resonance._original_definition.cache_clear()
        first=resonance.ResonanceAllocations.from_original(raw)
        self.assertIs(first,resonance.ResonanceAllocations.from_original(raw))
        with self.assertRaises(FrozenInstanceError):first.stats[0].maximum=1
        mutable=bytearray(raw)
        second=resonance.ResonanceAllocations.from_original(mutable)
        self.assertEqual(first,second)
        self.assertIsNot(first,second)
        mutable[-1]^=1
        with self.assertRaises(ValueError):resonance.ResonanceAllocations.from_original(mutable)
        with self.assertRaises(ValueError):resonance.ResonanceAllocations.from_original(raw+b' ')

    def test_cache_has_fixed_two_entry_bound(self):
        self.assertEqual(boost._original_definition.cache_parameters()['maxsize'],2)
        self.assertEqual(resonance._original_definition.cache_parameters()['maxsize'],2)
        self.assertNotIn('account',boost.BoostingDefinition.__dataclass_fields__)


class ParticipationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript('CREATE TABLE characters(uid INTEGER PRIMARY KEY,level INTEGER);'
            'CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER);'
            'INSERT INTO characters VALUES(1001,99);INSERT INTO character_owners VALUES(1001,1);')
        with self.db:
            self.db.execute('BEGIN')
            self.part=BoostingParticipation(self.db,RAW)
            self.part.initialize()
        self.binding=BoostingQuestBinding(RAW,clock=lambda:1,campaign_open=lambda *a:True)
        self.binding._store=lambda db:self.fail('eligibility must not construct a reward/profile store')
        self.session=SimpleNamespace(account=SimpleNamespace(account_id=1,uid=1001))

    def enroll(self):
        with self.db:
            self.db.execute('BEGIN')
            self.part.record_binding(account=1,character=1001,operation='own-join',joined_at=1)

    def test_unbound_then_joined_current_binding_not_cached(self):
        self.assertFalse(self.binding._participant(self.db,self.session))
        self.enroll()
        self.assertTrue(self.binding._participant(self.db,self.session))
        self.db.execute('UPDATE characters SET level=98')
        self.assertFalse(self.binding._participant(self.db,self.session))

    def test_foreign_owner_still_rejected(self):
        self.session.account.account_id=2
        with self.assertRaisesRegex(ValueError,'belong'):
            self.binding._participant(self.db,self.session)

    def test_corrupt_binding_rejected_even_when_below99(self):
        self.enroll()
        self.db.execute("UPDATE boosting2026_participation SET request_sha256='bad'")
        self.db.execute('UPDATE characters SET level=1')
        with self.assertRaises(ValueError):self.binding._participant(self.db,self.session)

    def test_read_only_participant_check_performs_no_DDL(self):
        self.enroll()
        self.db.commit()
        self.db.execute('PRAGMA query_only=ON')
        statements=[]
        self.db.set_trace_callback(statements.append)
        self.assertTrue(self.binding._participant(self.db,self.session))
        self.assertTrue(all(s.lstrip().upper().startswith('SELECT')for s in statements))


class WriterTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'owned.sqlite'
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY,level INTEGER)')
            db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER)')
            db.execute('INSERT INTO characters VALUES(1001,99)')
            db.execute('INSERT INTO character_owners VALUES(1001,1)')
            db.execute('CREATE TABLE location(uid INTEGER PRIMARY KEY,town INTEGER,board INTEGER,progress INTEGER,x REAL,y REAL,z REAL,revision INTEGER)')
            db.execute('INSERT INTO location VALUES(1001,1500,0,0,0,0,0,0)')

    def value(self):
        return dict(operation_id=str(uuid.uuid4()),account_id=1,amount=5,expected_balance=0,reason='owned fixture')

    def test_cash_credit_replay_and_metrics(self):
        value=self.value()
        sample={}
        with worker_timing(sample):
            first=ariel_cash.credit(self.path,value,validate=lambda a:None,now=lambda:1)
            again=ariel_cash.credit(self.path,value,validate=lambda a:None,now=lambda:2)
        self.assertEqual(first,again)
        self.assertEqual(first['after']['balance'],5)
        self.assertEqual(sample['sql_busy'],0)
        self.assertIn('sql_finish_wait_ms',sample)
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM ariel_cash_operations').fetchone(),(1,))

    def test_cash_late_validation_rolls_back_and_retry_applies_once(self):
        value=self.value()
        count=0
        def validate(account):
            nonlocal count
            count+=1
            if count==2:raise ValueError('late lease')
        sample={}
        with self.assertRaisesRegex(ValueError,'late lease'),worker_timing(sample):
            ariel_cash.credit(self.path,value,validate=validate,now=lambda:1)
        self.assertEqual(sample['sql_rollbacks'],1)
        with closing(sqlite3.connect(self.path))as db:
            self.assertFalse(ariel_cash.present(db,ariel_cash.TABLE))
        self.assertEqual(ariel_cash.credit(self.path,value,validate=lambda a:None,now=lambda:1)['after']['balance'],5)

    def test_cash_commit_busy_keeps_original_manual_rollback(self):
        value=self.value()
        ariel_cash.credit(self.path,value,validate=lambda a:None,now=lambda:1)
        value=dict(value,operation_id=str(uuid.uuid4()),expected_balance=5)
        connect=sqlite3.connect
        def short(*args,**kwargs):
            kwargs['timeout']=.02
            return connect(*args,**kwargs)
        with closing(connect(self.path))as reader:
            reader.execute('BEGIN')
            reader.execute('SELECT * FROM ariel_account_cash').fetchall()
            sample={}
            with patch.object(sqlite3,'connect',short),self.assertRaises(sqlite3.OperationalError),worker_timing(sample):
                ariel_cash.credit(self.path,value,validate=lambda a:None,now=lambda:1)
            self.assertEqual(sample['sql_busy'],1)
            self.assertEqual(sample['sql_finish_busy'],1)
            self.assertEqual(sample['sql_rollbacks'],1)
            reader.rollback()
        with closing(connect(self.path))as db:
            self.assertEqual(ariel_cash.balance(db,1)['balance'],5)
        self.assertEqual(ariel_cash.credit(self.path,value,validate=lambda a:None,now=lambda:1)['after']['balance'],10)

    def test_fishing_all_three_begin_contention_never_reaches_actor(self):
        connect=sqlite3.connect
        def short(*args,**kwargs):
            kwargs['timeout']=.02
            return connect(*args,**kwargs)
        with closing(connect(self.path))as owner:
            owner.execute('BEGIN IMMEDIATE')
            connection=str(uuid.uuid4());cycle=str(uuid.uuid4())
            calls=(lambda:fishing_attempt.start(self.path,1001,1,connection,lambda *a:None,lambda db:None),
                lambda:fishing_attempt.stop(self.path,1001,1,connection,cycle,lambda:None,lambda db:None),
                lambda:fishing_attempt.settle(self.path,1001,1,connection,cycle,0,lambda *a:None,lambda db:None))
            for call in calls:
                sample={}
                with patch.object(sqlite3,'connect',short),patch.object(fishing_attempt,'_actor',side_effect=AssertionError('must not execute')),self.assertRaises(sqlite3.OperationalError),worker_timing(sample):call()
                self.assertEqual(sample['sql_busy'],1)
                self.assertEqual(sample['sql_finish_busy'],0)
            owner.rollback()

    def test_fishing_stop_rollback_and_owner_qualified_retry(self):
        with closing(sqlite3.connect(self.path))as db,db:fishing_attempt.ensure(db)
        connection=str(uuid.uuid4());cycle=str(uuid.uuid4())
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('INSERT INTO fishing_active_epochs VALUES(1,1001,?,?,0,1,36,?)',(connection,cycle,'{}'))
        def fail():raise ValueError('encode')
        with self.assertRaisesRegex(ValueError,'encode'):
            fishing_attempt.stop(self.path,1001,1,connection,cycle,fail,lambda db:None)
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM fishing_active_epochs').fetchone(),(1,))
        self.assertEqual(fishing_attempt.stop(self.path,1001,1,connection,cycle,lambda:['encoded'],lambda db:None),['encoded'])
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM fishing_active_epochs').fetchone(),(0,))


class GMWriterTests(unittest.TestCase):
    def setUp(self):
        from els_server.domain.local_session import LocalAccount
        from els_server.storage.local_state import LocalState
        from els_server.domain.friends_world import Mailbox
        from els_server.gm_runtime import Runtime
        tmp=tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'owned-gm.sqlite'
        self.account=LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.account.enable_inventory()
        self.session=SimpleNamespace(account=self.account,mailbox=Mailbox())
        self.runtime=Runtime(SimpleNamespace(config=SimpleNamespace(state_file=self.path)),None,None)
        # Isolate the changed transaction/mailbox boundary. Actual native
        # account/session authentication is exercised by the retained TLS suite.
        self.runtime.session=lambda value:self.session
        self.value=dict(operation_id=str(uuid.uuid4()),template=77420,quantity=1,reason='owned fixture')

    def amount(self):
        from els_server.storage.inventory_state import load_items
        with closing(sqlite3.connect(self.path))as db:
            return sum(i['count']for i in load_items(db,1001)if i['template']==77420)

    def test_grant_publishes_after_commit_and_replay_does_not_repeat(self):
        before=self.amount();sample={}
        with worker_timing(sample):first=self.runtime.give(self.value)
        box=self.session.mailbox;length=len(box.messages)
        self.assertEqual(self.amount(),before+1)
        self.assertFalse(first['replayed'])
        self.assertTrue(self.runtime.give(self.value)['replayed'])
        self.assertIs(self.session.mailbox,box)
        self.assertEqual(len(box.messages),length)
        self.assertEqual(self.amount(),before+1)
        self.assertIn('sql_finish_wait_ms',sample)

    def test_encode_failure_rolls_back_before_mailbox_publication(self):
        before=self.amount();box=self.session.mailbox;sample={}
        with patch('els_server.gm_runtime.prepare_mailbox',side_effect=ValueError('encode')),self.assertRaisesRegex(ValueError,'encode'),worker_timing(sample):
            self.runtime.give(self.value)
        self.assertEqual(sample['sql_rollbacks'],1)
        self.assertEqual(self.amount(),before)
        self.assertIs(self.session.mailbox,box)
        self.runtime.give(self.value)
        self.assertEqual(self.amount(),before+1)

    def test_reader_blocks_commit_without_publishing_or_partial_grant(self):
        connect=sqlite3.connect
        def short(*args,**kwargs):
            kwargs['timeout']=.02
            return connect(*args,**kwargs)
        before=self.amount();box=self.session.mailbox;sample={}
        with closing(connect(self.path))as reader:
            reader.execute('BEGIN')
            reader.execute('SELECT * FROM inventory_items').fetchall()
            with patch.object(sqlite3,'connect',short),self.assertRaises(sqlite3.OperationalError),worker_timing(sample):
                self.runtime.give(self.value)
            self.assertEqual(sample['sql_busy'],1)
            self.assertEqual(sample['sql_finish_busy'],1)
            self.assertIs(self.session.mailbox,box)
            reader.rollback()
        self.assertEqual(self.amount(),before)
        self.runtime.give(self.value)
        self.assertEqual(self.amount(),before+1)

    def test_external_writer_rejected_before_session_or_grant(self):
        connect=sqlite3.connect
        def short(*args,**kwargs):
            kwargs['timeout']=.02
            return connect(*args,**kwargs)
        with closing(connect(self.path))as owner:
            owner.execute('BEGIN IMMEDIATE');sample={}
            with patch.object(sqlite3,'connect',short),patch.object(self.runtime,'session',side_effect=AssertionError('not reached')),self.assertRaises(sqlite3.OperationalError),worker_timing(sample):
                self.runtime.give(self.value)
            self.assertEqual(sample['sql_busy'],1)
            self.assertEqual(sample['sql_finish_busy'],0)
            owner.rollback()
