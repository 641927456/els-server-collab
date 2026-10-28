"""First-use/receipt regression against a selected current-engine materialization.

The frozen PR597 module is a negative control only; it is never installed.
Set ELS_PR597_RUNTIME_ROOT to the materialized ONLINE or LOCAL source root.
All SQL writes are restricted to this test's own temporary directory.
"""
from contextlib import closing
from pathlib import Path
import hashlib
import ast
import types
import json
import os
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNTIME=os.environ.get('ELS_PR597_RUNTIME_ROOT')
if RUNTIME:
    sys.path.insert(0,str(Path(RUNTIME).resolve()))

NEGATIVE_SHA='ad657f83afc3e56970ec4b7b0d037012507e21dc85b6a0731482d61971aa9d26'
REFERENCE=Path(__file__).resolve().parents[1]/'references/pr597-skill-book-regression-20261028-v1'


class PR597SkillBookRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RUNTIME:
            raise unittest.SkipTest('Run against each current-engine materialization, not checkout root sources')
        root=Path(RUNTIME).resolve()
        receipt=json.loads((root/'engine-source-receipt.json').read_bytes())
        entries={r['path']:r for r in receipt['files']}
        expected=entries['els_server/storage/skill_unlocks.py']
        from els_server.storage import skill_unlocks
        cls.module=skill_unlocks
        selected=Path(skill_unlocks.__file__).resolve()
        if selected!=root/'els_server/storage/skill_unlocks.py':
            raise AssertionError('Imported checkout-root or another runtime skill_book module')
        if hashlib.sha256(selected.read_bytes()).hexdigest()!=expected['sha256']:
            raise AssertionError('Current-engine materialization does not match its source receipt')
        cls.root=root

    def setUp(self):
        temp_parent=os.environ.get('ELS_PR597_TEST_TEMP_ROOT')
        self.temp=tempfile.TemporaryDirectory(prefix='pr597-book-',dir=temp_parent)
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'game.sqlite3'

    def arrange(self):
        from els_server.domain.local_session import LocalAccount
        from els_server.storage.local_state import LocalState
        self.account=LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1,master=1 WHERE uid=1001')
            db.execute("INSERT OR REPLACE INTO character_artifacts VALUES(1001,1,1,1,0,'[0,0,0,0]')")

    def dump(self):
        with closing(sqlite3.connect(self.path))as db:
            return tuple(db.iterdump())

    def has_receipt_table(self):
        with closing(sqlite3.connect(self.path))as db:
            return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_book_receipts'").fetchone()is not None

    def book(self,group=5,quantity=1):
        from els_server.domain.skill_unlocks import catalog
        from els_server.storage.inventory_state import grant_items
        row=next(r for r in catalog()['books'].values()if r['seal_group']==group)
        with closing(sqlite3.connect(self.path))as db,db:
            item=grant_items(db,[dict(template=row['template'],metadata=0,group=4,quantity=quantity)],1001)[0]
        return item,struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)


    def test_first_use_replay_conflict_and_cold_read(self):
        self.arrange();item,payload=self.book(quantity=1)
        self.assertFalse(self.has_receipt_table())
        receipt=self.module.use_skill_book(self.path,1001,payload,'first-book')
        self.assertFalse(receipt['replayed'])
        self.assertEqual(receipt['notification'].kind,0x131)
        self.assertEqual(receipt['quest_notification'].kind,0x2b)
        self.assertTrue(self.has_receipt_table())
        with closing(sqlite3.connect(self.path))as db:
            self.assertIsNone(db.execute('SELECT count FROM inventory_items WHERE uid=?',(item['uid'],)).fetchone())
            self.assertEqual(db.execute('SELECT seal_group FROM character_skill_seals WHERE owner=1001').fetchall(),[(5,)])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM skill_book_receipts').fetchone(),(1,))
        before=self.dump();replayed=self.module.use_skill_book(self.path,1001,payload,'first-book')
        self.assertTrue(replayed['replayed']);self.assertNotIn('notification',replayed)
        self.assertEqual(self.dump(),before)
        from els_server.domain.local_session import LocalAccount
        from els_server.storage.local_state import LocalState
        cold=LocalAccount(LocalState(self.path));cold.enable_characters()
        self.assertEqual(cold.character()['skill_seal_groups'],(5,))
        replacement,changed=self.book(group=1);before=self.dump()
        with self.assertRaisesRegex(ValueError,'Conflicting skill book retry'):
            self.module.use_skill_book(self.path,1001,changed,'first-book')
        self.assertEqual(self.dump(),before)

    def test_foreign_inventory_and_duplicate_group_do_not_consume(self):
        self.arrange();item,payload=self.book()
        other=self.account.characters.create('BookOther',2,'book-regression-other')['uid']
        before=self.dump()
        self.assertIsNone(self.module.use_skill_book(self.path,other,payload,'foreign-book'))
        self.assertEqual(self.dump(),before)
        self.module.use_skill_book(self.path,1001,payload,'owned-book')
        duplicate,again=self.book();before=self.dump()
        with self.assertRaises(ValueError):self.module.use_skill_book(self.path,1001,again,'duplicate-book')
        self.assertEqual(self.dump(),before)

    def test_failure_after_new_receipt_insert_rolls_back_item_and_schema(self):
        self.arrange();item,payload=self.book()
        before=self.dump();self.assertFalse(self.has_receipt_table())
        def fail_after_write(db,uid):
            self.assertEqual(db.execute('SELECT COUNT(*) FROM skill_book_receipts').fetchone(),(1,))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM inventory_items WHERE uid=?',(item['uid'],)).fetchone(),(0,))
            raise ValueError('injected post-write native quest serialization failure')
        with patch.object(self.module,'quest_refresh',side_effect=fail_after_write):
            with self.assertRaisesRegex(ValueError,'injected post-write'):
                self.module.use_skill_book(self.path,1001,payload,'rollback-book')
        self.assertEqual(self.dump(),before);self.assertFalse(self.has_receipt_table())
        self.assertFalse(self.module.use_skill_book(self.path,1001,payload,'rollback-book')['replayed'])


class PR597FrozenSkillBookNegativeControl(unittest.TestCase):
    def test_frozen_old_first_request_without_table_is_negative_control(self):
        raw=(REFERENCE/'old-pr597-skill_unlocks.py').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),NEGATIVE_SHA)
        # Execute the complete frozen original function, unchanged. Only its
        # import-only dependencies beyond the failing guard are stubbed; the
        # request parser and UID validator are actual checkout functions.
        repo=Path(__file__).resolve().parents[1]
        namespace=dict(closing=closing,sqlite3=sqlite3,hashlib=hashlib,struct=struct)
        def define(source,name):
            node=next(n for n in ast.parse(source).body
                      if isinstance(n,ast.FunctionDef)and n.name==name)
            exec(compile(ast.Module(body=[node],type_ignores=[]),name,'exec'),namespace)
        define((repo/'els_server/protocol/career_messages.py').read_text('utf8'),'use_request')
        define((repo/'els_server/storage/character_schema.py').read_text('utf8'),'character_uid')
        define(raw.decode('utf8'),'use_skill_book')
        domain=types.ModuleType('els_server.domain.skill_unlocks')
        def beyond_guard(*args,**kwargs):raise AssertionError('Negative control passed old unbound guard')
        domain.catalog=domain.validate_unlock=domain.unlock_notice=beyond_guard
        characters=types.ModuleType('els_server.storage.characters');characters.Characters=object
        temporary=tempfile.TemporaryDirectory(prefix='pr597-old-book-',dir=os.environ.get('ELS_PR597_TEST_TEMP_ROOT'))
        self.addCleanup(temporary.cleanup)
        path=Path(temporary.name)/'empty.sqlite3'
        with closing(sqlite3.connect(path))as db:db.execute('SELECT 1')
        before=path.read_bytes()
        with patch.dict(sys.modules,{domain.__name__:domain,characters.__name__:characters}):
            with self.assertRaisesRegex(UnboundLocalError,"old"):
                namespace['use_skill_book'](path,1001,struct.pack('>QQiiIB',123456789,0,0,0,0,0),'first-book-no-table')
        self.assertEqual(path.read_bytes(),before)
        with closing(sqlite3.connect(path))as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_book_receipts'").fetchone())


if __name__=='__main__':
    unittest.main(verbosity=2)
