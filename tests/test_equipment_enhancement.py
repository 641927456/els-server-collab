import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.equipment_enhancement import replace,exists
from els_server.domain.inventory_items import item_body
from els_server.domain.equipment_enhancement import validate


class EnhancementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.db';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.plan=dict(template=60100,metadata=1,quantity=1,group=1)

    def test_native_field_boundaries_and_optional_layout(self):
        plain=dict(uid=1,template=60100,metadata=1,count=1,group=1,slot=0,durability=10000)
        for extended in (False,True):
            item=dict(plain,attributes=[1,0,0,0],expires_at=1798732799) if extended else plain
            before=item_body(item)
            for level in range(21):
                body=item_body(dict(item,enhancement=level))
                self.assertEqual(body[:12],before[:12]);self.assertEqual(body[13:],before[13:]);self.assertEqual(body[12],level)
        for invalid in (-1,21,True,1.0):
            with self.assertRaises(ValueError):validate(60100,invalid)
        with self.assertRaises(ValueError):validate(77000,1)

    def test_legacy_read_no_migration_and_cas_rollback(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            item=grant_items(db,[self.plan])[0]
        with closing(sqlite3.connect(self.path)) as db:
            self.assertFalse(exists(db));before=list(db.iterdump());load_items(db);self.assertEqual(before,list(db.iterdump()))
            with self.assertRaises(ValueError):replace(db,1001,item['uid'],0,7)
            db.execute('BEGIN IMMEDIATE');replace(db,1001,item['uid'],0,7)
            with self.assertRaises(ValueError):replace(db,1001,item['uid'],0,10)
            with self.assertRaises(ValueError):replace(db,1002,item['uid'],7,10)
            db.rollback();self.assertFalse(exists(db));self.assertEqual(before,list(db.iterdump()))

    def test_grant_move_stats_and_reopen(self):
        from els_server.storage.equipment_moves import move_equipment
        from els_server.domain.character_stats import instance_attributes
        from els_server.domain.instance_stats import normal_instance_attributes
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET unit_class=100,level=40 WHERE uid=1001')
            items=grant_items(db,[dict(self.plan,quantity=2,enhancement=7)])
        self.assertEqual(len(items),2);self.assertNotEqual(items[0]['uid'],items[1]['uid'])
        move_equipment(self.path,struct.pack('>BiBiB',1,0,9,9,0))
        move_equipment(self.path,struct.pack('>BiBiB',1,1,9,9,0))
        saved=self.account.get_inventory_snapshot();self.assertTrue(all(i['enhancement']==7 for i in saved['items']))
        other=LocalAccount(LocalState(self.path));other.enable_characters();self.assertEqual(other.get_inventory_snapshot(),saved)
        char=dict(unit_class=100,unit_type=1,level=40)
        self.assertEqual(instance_attributes(items[0],char),normal_instance_attributes(60100,char,enhancement=7))
        self.assertNotEqual(instance_attributes(items[0],char),normal_instance_attributes(60100,char))
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');replace(db,1001,items[0]['uid'],7,0)
            self.assertNotIn('enhancement',next(i for i in load_items(db) if i['uid']==items[0]['uid']))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_expiry_and_encoding_failure_roll_back(self):
        from els_server.storage.item_expiration import remove_due
        deadline=1792056000
        with patch('time.time',return_value=deadline),closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');item=grant_items(db,[dict(self.plan,enhancement=10,expires_at=deadline)])[0]
        with patch('time.time',return_value=deadline+1),closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(ValueError):replace(db,1001,item['uid'],10,11)
        with patch('els_server.protocol.expiration_messages.notice',side_effect=RuntimeError('encode')):
            with self.assertRaises(RuntimeError):remove_due(self.path,1001,now=deadline+1)
        self.assertEqual(self.account.get_inventory_snapshot()['items'][0]['enhancement'],10)
        remove_due(self.path,1001,now=deadline+1)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT * FROM equipment_enhancement').fetchall(),[])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
