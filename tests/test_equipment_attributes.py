import json,sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.equipment_attributes import replace_attributes
from els_server.domain.inventory_items import item_body,validate_item,inventory_restore_map
from els_server.domain.equipment_attributes import inventory_definitions


class EquipmentAttributesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.other=self.account.characters.create('AttrOther',5,'other')['uid'];self.account.for_character(self.other)
        self.other_items=self.account.for_character(self.other).get_inventory_snapshot()['items']
        with closing(sqlite3.connect(self.path)) as db,db:
            self.item=grant_items(db,[dict(template=30154,metadata=1,quantity=1,group=1)])[0]

    def test_native_variable_body_and_no_changes_to_other_fields(self):
        baseline=item_body(self.item);self.assertEqual(len(baseline),304)
        for slots in ([1,0,0,0],[1,4,0,0],[1,0,4,0],[0,0,0,6],[0,0,0,0]):
            item={**self.item,'attributes':slots};body=item_body(item)
            if any(slots):
                self.assertEqual(len(body),320);self.assertEqual(body[:13],baseline[:13]);self.assertEqual(body[33:],baseline[17:])
                self.assertEqual(struct.unpack_from('>I4i',body,13),(4,*slots))
            else:self.assertEqual(body,baseline)
        for slots in ([1,2,0,0],[4,5,0,0],[1]*4,[7,0,0,0],[False,0,0,0],[]):
            with self.assertRaises(ValueError):validate_item({**self.item,'attributes':slots})
        with self.assertRaises(ValueError):validate_item({**self.item,'count':2,'attributes':[1,0,0,0]})
        self.assertEqual(len(inventory_definitions()),10)

    def test_persistence_restart_owner_check_and_clear(self):
        before=self.account.get_reward_balances()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');replace_attributes(db,1001,self.item['uid'],[0]*4,[1,4,0,0])
        restarted=LocalAccount(LocalState(self.path));restarted.enable_characters()
        items=restarted.get_inventory_snapshot()['items'];self.assertEqual(items[0]['attributes'],[1,4,0,0])
        self.assertEqual(len(inventory_restore_map(items)),4+8+340)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            self.assertEqual(load_items(db,self.other),self.other_items)
            with self.assertRaises(ValueError):replace_attributes(db,self.other,self.item['uid'],[1,4,0,0],[0]*4)
            with self.assertRaises(ValueError):replace_attributes(db,1001,self.item['uid'],[0]*4,[1,0,0,0])
            replace_attributes(db,1001,self.item['uid'],[1,4,0,0],[0]*4)
        self.assertNotIn('attributes',self.account.get_inventory_snapshot()['items'][0])
        self.assertEqual(before,self.account.get_reward_balances())

    def test_rollback_and_competing_updates(self):
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(ValueError):replace_attributes(db,1001,self.item['uid'],[0]*4,[1,0,0,0])
            db.execute('BEGIN IMMEDIATE');replace_attributes(db,1001,self.item['uid'],[0]*4,[1,0,0,0]);db.rollback()
        self.assertNotIn('attributes',self.account.get_inventory_snapshot()['items'][0])
        def attempt(target):
            try:
                with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
                    db.execute('BEGIN IMMEDIATE');replace_attributes(db,1001,self.item['uid'],[0]*4,[target,0,0,0])
                return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,[1,2]))
        self.assertEqual(sum(results),1)
