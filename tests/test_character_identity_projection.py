from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from els_server.storage.characters import Characters
from els_server.domain.attendance_2026_online import selected_local_test_character


class IdentityReads(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT)
        self.path=Path(self.temp.name)/'state.sqlite3'
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE characters(uid PRIMARY KEY,name,unit_type,unit_class,level,transcendence,master,revision)')
            db.execute('CREATE TABLE character_owners(uid PRIMARY KEY,account_id)')
            db.executemany('INSERT INTO characters VALUES (?,?,?,?,?,?,?,?)',
                           [(1008,'OwnedEve',5,162,99,1,1,4),(1009,'Foreign',1,1,99,0,0,0)])
            db.executemany('INSERT INTO character_owners VALUES (?,?)',[(1008,2),(1009,3)])
        self.roster=Characters.__new__(Characters)
        self.roster.path=self.path;self.roster.account_id=2

    def tearDown(self):
        assert Path(self.temp.name).resolve().parent==ROOT.resolve()
        self.temp.cleanup()

    def test_owned_current_identity_without_extended_tables(self):
        expected=dict(uid=1008,name='OwnedEve',unit_type=5,unit_class=162,level=99,
                      transcendence=True,master=True,revision=4)
        self.assertEqual(self.roster.identity(1008),expected)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=8,revision=5 WHERE uid=1008')
        self.assertEqual(self.roster.identity(1008)['level'],8)
        with self.assertRaisesRegex(ValueError,'Unknown character'):
            self.roster.identity(1009)

    def test_finalized_deletion_remains_ineligible(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE character_lifecycle(uid PRIMARY KEY,finalized_at)')
            db.execute('INSERT INTO character_lifecycle VALUES (1008,0)')
        self.assertEqual(self.roster.identity(1008)['uid'],1008)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE character_lifecycle SET finalized_at=123 WHERE uid=1008')
        with self.assertRaisesRegex(ValueError,'Unknown character'):
            self.roster.identity(1008)

    def test_eligibility_still_checks_owner_level_phase_disabled_and_lease(self):
        def forbidden():raise AssertionError('Eligibility must not load full wire state')
        account=SimpleNamespace(account_id=2,uid=1008,characters=self.roster,
                                store=SimpleNamespace(path=self.path),character=forbidden,
                                character_identity=lambda:self.roster.identity(account.uid))
        enabled=[True]
        app=SimpleNamespace(registry=SimpleNamespace(enabled=lambda _:enabled[0]),playing={})
        s=SimpleNamespace(role='game',client_build='dx11_260923',phase='town_ready',
                          released=False,account=account,identity={'id':2},application=app)
        app.playing[2]=s
        self.assertEqual(selected_local_test_character(s),(str(self.path),2,1008,99))
        enabled[0]=False;self.assertIsNone(selected_local_test_character(s));enabled[0]=True
        app.playing.clear();self.assertIsNone(selected_local_test_character(s));app.playing[2]=s
        s.phase='new';self.assertIsNone(selected_local_test_character(s));s.phase='town_ready'
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=8 WHERE uid=1008')
        self.assertIsNone(selected_local_test_character(s))
        account.uid=1009
        with self.assertRaisesRegex(ValueError,'Unknown character'):
            selected_local_test_character(s)


if __name__=='__main__':unittest.main(verbosity=2)
