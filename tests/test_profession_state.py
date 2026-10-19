"""Persistence invariants; synthetic states are not starting/growth policy."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.storage.profession_state import snapshot, replace, exists
from els_server.protocol.profession_messages import ProfessionState, state_wire
from els_server.protocol.local_messages import character_unit, character_list, player_initialization


class ProfessionStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'save.db'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.state = ProfessionState(2, 7, 100, {9: 10, -1: 3}, 20, 80)

    def test_legacy_reads_keep_default_wire_and_do_not_migrate(self):
        before_character = self.account.character()
        without = dict(before_character)
        without.pop('profession')
        without.pop('profession_revision')
        self.assertEqual(character_unit(character=before_character), character_unit(character=without))
        with closing(sqlite3.connect(self.path)) as db:
            before = list(db.iterdump())
            self.assertEqual(snapshot(db, 1001, 1), dict(state=asdict(ProfessionState()), revision=0))
            self.account.characters.list()
            self.assertFalse(exists(db))
            self.assertEqual(before, list(db.iterdump()))
            with self.assertRaises(ValueError): replace(db, 1001, 1, 0, self.state)
            db.execute('BEGIN IMMEDIATE')
            replace(db, 1001, 1, 0, ProfessionState())
            self.assertFalse(exists(db))

    def test_owner_and_version_checks_and_transaction_rollback(self):
        eve = self.account.characters.create('EveTest', 5, 'eve')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE character_owners SET account_id=2 WHERE uid=?', (eve['uid'],))
        with closing(sqlite3.connect(self.path)) as db:
            before = list(db.iterdump())
            db.execute('BEGIN IMMEDIATE')
            for uid, account in ((1001, 2), (eve['uid'], 1), (9999, 1), (1001, True)):
                with self.assertRaises(ValueError): replace(db, uid, account, 0, self.state)
            self.assertEqual(replace(db, 1001, 1, 0, self.state)['revision'], 1)
            with self.assertRaises(ValueError): replace(db, 1001, 1, 0, self.state)
            self.assertEqual(snapshot(db, eve['uid'], 2)['revision'], 0)
            db.rollback()
            self.assertEqual(before, list(db.iterdump()))
            self.assertFalse(exists(db))

    def test_reopen_character_list_and_initialization_restore_identical_state(self):
        before = self.account.character()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            replace(db, 1001, 1, 0, self.state)
        restored = Characters(self.path).get(1001)
        self.assertEqual(restored['profession'], asdict(self.state))
        self.assertEqual(restored['profession_revision'], 1)
        self.assertEqual(restored['revision'], before['revision']+1)
        # Both public packet builders consume the same character_unit encoder.
        unit = character_unit(character=restored)
        self.assertIn(state_wire(self.state), unit)
        self.assertIn(unit, character_list('dx11_260923', characters=[dict(restored, items=[])]).payload)
        self.assertIn(unit, player_initialization(character=restored).payload)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            replace(db, 1001, 1, 1, ProfessionState())
            self.assertEqual(snapshot(db, 1001, 1)['revision'], 2)
            with self.assertRaises(ValueError): replace(db, 1001, 1, 0, self.state)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_corrupt_or_unencodable_state_fails_without_writes(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            for bad in (ProfessionState(4), ProfessionState(1, 256),
                        ProfessionState(counters={1: 1.5}), ProfessionState(progress=-1)):
                with self.assertRaises(ValueError): replace(db, 1001, 1, 0, bad)
            self.assertFalse(exists(db))
            replace(db, 1001, 1, 0, self.state)
        for invalid in ('[[1,2],[1,3]]', '[[true,1]]', '{"1":2}', '[[1,1.5]]'):
            with closing(sqlite3.connect(self.path)) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE character_professions SET counters=?', (invalid,))
                before = list(db.iterdump())
                with self.assertRaises(ValueError): snapshot(db, 1001, 1)
                with self.assertRaises(ValueError): replace(db, 1001, 1, 1, self.state)
                self.assertEqual(before, list(db.iterdump()))
                db.rollback()
