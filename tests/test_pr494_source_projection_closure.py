"""Public source interfaces: private SQL only, no App, listener or gameplay."""
import hashlib
import inspect
import json
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from els_server.domain.acquisition_policy import can_acquire
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.domain.raid_reward_items import _issue_source
from els_server.storage.inventory_state import grant_items, load_items, validate_plan
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount


class SourceProjectionClosure(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'source-closure.db'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()

    def plan(self, template):
        return [dict(template=template, metadata=VERIFIED_TEMPLATES[template],
                     group=TEMPLATE_BAG_GROUPS[template], quantity=1)]

    def connect(self):
        db = sqlite3.connect(self.path)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        return db

    def source(self, db, operation, plan):
        # Controlled private already-authorized-writer fixture; not an entry,
        # clear, combat or reward-policy integration test.
        return _issue_source(db, 1001, operation, 'phase', {'fixture': 'source-interface'},
                             plan, lambda writer: writer is db and db.in_transaction)

    def test_actual_clear_keyword_shape_accepts_none_and_old_default_call(self):
        signature = inspect.signature(self.account.reward_store.grant)
        signature.bind(str(uuid.uuid4()), b'proof', 0, 0, lambda b: b'ok',
                       raid_reward_source=None, silver_source=None, daily_special=None)
        for kwargs in ({}, dict(raid_reward_source=None, silver_source=None)):
            result = self.account.reward_store.grant(str(uuid.uuid4()), b'plain', 0, 0,
                                                     lambda b: b'plain-ok', **kwargs)
            self.assertFalse(result['replayed'])

    def test_typed_raid_circuit_atomic_receipt_replay_and_cold_options(self):
        operation = str(uuid.uuid4())
        plan = self.plan(118590)
        self.assertFalse(can_acquire(118590))
        with closing(self.connect()) as db, db:
            source = self.source(db, operation, plan)
            result = self.account.reward_store.grant(operation, b'phase', 0, 0,
                lambda b: b'phase-ok', item_plan=plan, transaction=db,
                raid_reward_source=source)
            self.assertEqual(result['items'][0]['template'], 118590)
            self.assertEqual(len(result['items'][0]['option_groups']['1']), 1)
            after = list(db.iterdump())
            replay = self.account.reward_store.grant(operation, b'phase', 0, 0,
                lambda b: self.fail('Replay rebuilt response'), item_plan=plan,
                transaction=db, raid_reward_source=source)
            self.assertTrue(replay['replayed'])
            self.assertEqual(after, list(db.iterdump()))
        with closing(sqlite3.connect(self.path)) as db:
            saved = next(i for i in load_items(db) if i['template'] == 118590)
            self.assertEqual(saved['option_groups'], result['items'][0]['option_groups'])
            self.assertEqual(db.execute('SELECT count(*) FROM reward_receipts WHERE run_id=?',
                                        (operation,)).fetchone()[0], 1)

    def test_typed_raid_response_failure_rolls_back_items_money_and_receipt(self):
        operation = str(uuid.uuid4())
        plan = self.plan(118590)
        with closing(self.connect()) as db, db:
            source = self.source(db, operation, plan)
            before = list(db.iterdump())
            def refuse(balance):
                raise ValueError('controlled complete reward response failure')
            with self.assertRaisesRegex(ValueError, 'controlled complete'):
                self.account.reward_store.grant(operation, b'phase', 0, 0, refuse,
                    item_plan=plan, transaction=db, raid_reward_source=source)
            self.assertEqual(before, list(db.iterdump()))

    def test_forged_and_mixed_regional_daily_raid_sources_refuse(self):
        plan = self.plan(118590)
        with closing(self.connect()) as db, db:
            for source in ({}, object()):
                with self.assertRaises(ValueError):
                    grant_items(db, plan, raid_reward_source=source)
            source = self.source(db, str(uuid.uuid4()), plan)
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                grant_items(db, plan, raid_reward_source=source, regional_cube_source=object())
            with self.assertRaises(ValueError):
                validate_plan(plan, raid_reward_source=source, daily_special_source=object())
            with self.assertRaises(ValueError):
                grant_items(db, plan, 1002, raid_reward_source=source)
            self.assertEqual(before, list(db.iterdump()))

    def test_silver_writer_proof_binding_and_persisted_exact_plan(self):
        from els_server.domain.silver_mirror_rewards import ClearSource
        from els_server.storage.silver_mirror_state import ensure
        operation = str(uuid.uuid4())
        proof = b'private accepted mirror-clear fixture'
        with closing(self.connect()) as db, db:
            ensure(db)
            db.execute('INSERT INTO silver_mirror_runs VALUES (?,?,?,?,?,?,?,?,?,?)',
                (operation, 1001, 1, 'private', 35710, 0, '0' * 64, 0,
                 hashlib.sha256(proof).hexdigest(), json.dumps(dict(slot=0, dungeon=35710))))
            db.execute('INSERT INTO silver_mirror_seeds VALUES (?,?)', (operation, '0' * 64))
            source = ClearSource(db, 1001, operation)
            before = list(db.iterdump())
            with self.assertRaises(ValueError):
                self.account.reward_store.grant(operation, b'wrong proof', 0, 0,
                    lambda b: b'ok', item_plan=source.plan, transaction=db, silver_source=source)
            self.assertEqual(before, list(db.iterdump()))
            result = self.account.reward_store.grant(operation, proof, 0, 0,
                lambda b: b'mirror-ok', item_plan=source.plan, transaction=db, silver_source=source)
            self.assertEqual({i['template'] for i in result['items']},
                             {p['template'] for p in source.plan})
        with closing(sqlite3.connect(self.path)) as db:
            self.assertTrue(any(i['template'] == 30870 for i in load_items(db)))


if __name__ == '__main__':
    unittest.main()
