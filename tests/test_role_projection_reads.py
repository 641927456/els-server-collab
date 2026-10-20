"""Portable ownership/query regressions; static title consumers use fixture DTOs."""
from contextlib import closing
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import ast
import json
import sqlite3
import sys
import tempfile
import unittest

from els_server.storage.characters import Characters
from els_server.storage import character_lifecycle as lifecycle


class RoleProjectionReads(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='role-projection-')
        temporary_path = Path(self.temporary.name).resolve()
        assert temporary_path.parent == Path(tempfile.gettempdir()).resolve()
        assert temporary_path.name.startswith('role-projection-')
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'synthetic.sqlite3'
        self.characters = Characters(self.path, 7)
        # The portable test supplies no retail title definitions or reward pool.
        # All role SQL, owner checks, artifacts and lifecycle readers stay real.
        title_dto = ModuleType('els_server.storage.titles')
        title_dto.snapshot = lambda db, uid: {'title': 0}
        title_dto.completed_for_equipment = lambda db, uid: tuple(
            r[0] for r in db.execute('SELECT quest FROM completed_quests WHERE owner=? ORDER BY quest', (uid,)))
        # Execute the unchanged pure reader without skill_unlocks' unrelated
        # eager fashion-catalog imports, which belong to locked runtime assets.
        unlock_reader = ModuleType('els_server.storage.skill_unlocks')
        source = Path(__file__).resolve().parents[1] / 'els_server/storage/skill_unlocks.py'
        saved_groups = next(node for node in ast.parse(source.read_text(encoding='utf-8-sig')).body
                            if isinstance(node, ast.FunctionDef) and node.name == 'saved_groups')
        exec(compile(ast.Module(body=[saved_groups], type_ignores=[]),
                     'els_server/storage/skill_unlocks.py', 'exec'), unlock_reader.__dict__)
        stub = patch.dict(sys.modules, {'els_server.storage.titles': title_dto,
                                      'els_server.storage.skill_unlocks': unlock_reader})
        stub.start()
        self.addCleanup(stub.stop)
        with closing(sqlite3.connect(self.path)) as db, db:
            for uid, owner in ((2001, 7), (2002, 7), (4001, 9)):
                db.execute('INSERT INTO characters VALUES (?,?,?,?,?,50,1,0,3)',
                           (uid, 'Synthetic' + str(uid), 'synthetic' + str(uid), 1, 1))
                db.execute('INSERT INTO character_owners VALUES (?,?)', (uid, owner))
            lifecycle.initialize(db)
            db.execute('INSERT INTO character_lifecycle VALUES (2001,7,1,0,0,0,0,0)')
            db.execute('INSERT INTO character_lifecycle VALUES (2002,7,1,10,30,20,0,0)')
            db.execute('CREATE TABLE completed_quests(owner INTEGER,quest INTEGER)')
            db.execute('INSERT INTO completed_quests VALUES (2001,17)')
            db.execute('CREATE TABLE dungeon_records(uid INTEGER,map_id INTEGER)')
            db.execute('INSERT INTO dungeon_records VALUES (2001,20000)')
            db.execute('CREATE TABLE character_ep(uid INTEGER PRIMARY KEY,ep INTEGER,revision INTEGER)')
            db.execute('INSERT INTO character_ep VALUES (2001,12,1)')
            db.execute('CREATE TABLE character_skill_expansions(uid INTEGER PRIMARY KEY,ordinary INTEGER)')
            db.execute('INSERT INTO character_skill_expansions VALUES (2001,1)')
            db.execute('CREATE TABLE character_skill_seals(owner INTEGER,seal_group INTEGER)')
            db.execute('INSERT INTO character_skill_seals VALUES (2001,2)')
            db.execute('CREATE TABLE character_bag_capacities(owner INTEGER,bag_group INTEGER,capacity INTEGER)')
            db.execute('INSERT INTO character_bag_capacities VALUES (2001,1,44)')
            db.execute('INSERT INTO character_artifacts VALUES (2001,1,2,3,4,?)', (json.dumps([11, 17]),))

    def test_complete_owned_list_get_and_single_identity_projection(self):
        roles = self.characters.list()
        self.assertEqual([r['uid'] for r in roles], [2001, 2002])
        self.assertEqual(roles, [self.characters.get(2001), self.characters.get(2002)])
        self.assertEqual(roles[0], dict(
            uid=2001, name='Synthetic2001', unit_type=1, unit_class=1, level=50,
            transcendence=True, master=False, revision=3,
            pending_delete=False, delete_at=0, delete_cooldown_until=0,
            resonance=dict(account_id=7, enabled=False, experience=0, level=0, auxiliary=0, revision=0),
            title=0, title_completed_quests=(17,),
            artifact=dict(template=1, evolution=2, level=3, experience=4, potentials=[11, 17]),
            cleared_dungeons=(20000,), ep=12, skill_row_expanded=True,
            skill_seal_groups=(2,), bag_capacities={1: 44},
            profession=dict(profession=0, level=0, experience=0, counters={}, progress=0, required=0),
            profession_revision=0))
        self.assertTrue(roles[1]['pending_delete'])
        self.assertEqual((roles[1]['delete_at'], roles[1]['delete_cooldown_until']), (30, 20))
        self.assertIsNone(roles[1]['artifact'])
        self.assertNotIn('ep', roles[1])
        original = Characters._row
        seen = []

        def row(value):
            if value is not None:
                seen.append(value[0])
            return original(value)

        with patch.object(Characters, '_row', staticmethod(row)):
            self.assertEqual(self.characters.get(2001), roles[0])
        self.assertEqual(seen, [2001])
        for uid in (4001, 8999, True, 1000):
            with self.assertRaises(ValueError):
                self.characters.get(uid)

    def test_artifact_isolation_and_final_delete_eligibility(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO character_artifacts VALUES (4001,1,1,1,0,'invalid-foreign-json')")
        self.assertEqual(len(self.characters.list()), 2)
        self.assertEqual(self.characters.get(2001)['artifact']['potentials'], [11, 17])
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO character_artifacts VALUES (2002,1,1,1,0,'invalid-sibling-json')")
        self.assertEqual(self.characters.get(2001)['uid'], 2001)
        with self.assertRaises(json.JSONDecodeError):
            self.characters.list()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE character_lifecycle SET finalized_at=40 WHERE uid=2002')
        self.assertEqual([r['uid'] for r in self.characters.list()], [2001])
        with self.assertRaisesRegex(ValueError, 'Unknown character'):
            self.characters.get(2002)

    def test_current_external_commit_rollback_and_owner_change(self):
        prior = self.characters.get(2001)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE characters SET level=88 WHERE uid=2001')
            db.rollback()
        self.assertEqual(self.characters.get(2001), prior)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE characters SET level=77,revision=9 WHERE uid=2001')
            db.execute("UPDATE character_artifacts SET potentials='[9,8]' WHERE uid=2001")
        current = self.characters.get(2001)
        self.assertEqual((current['level'], current['revision']), (77, 9))
        self.assertEqual(current['artifact']['potentials'], [9, 8])
        self.assertEqual(prior['artifact']['potentials'], [11, 17])
        self.assertEqual(Characters(self.path, 7).get(2001), current)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE character_owners SET account_id=9 WHERE uid=2001')
        with self.assertRaisesRegex(ValueError, 'Unknown character'):
            self.characters.get(2001)

    def test_lifecycle_default_contract_and_legacy_variable_limit(self):
        with closing(sqlite3.connect(self.path)) as db:
            all_rows = lifecycle.states(db)
            db.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
            statements = []
            db.set_trace_callback(statements.append)
            requested = tuple(range(1001, 2502))
            self.assertEqual(lifecycle.states(db, requested),
                             {uid: row for uid, row in all_rows.items() if uid in requested})
            selected = [sql for sql in statements if sql.startswith('SELECT * FROM character_lifecycle WHERE uid IN')]
            self.assertEqual(len(selected), 2)
            self.assertEqual(lifecycle.states(db, ()), {})
            self.assertEqual(lifecycle.decorate(db, iter([])), [])
            self.assertEqual(lifecycle.states(db), all_rows)


if __name__ == '__main__':
    unittest.main()
