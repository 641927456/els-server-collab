import sqlite3,struct,tempfile,unittest
from contextlib import closing
from pathlib import Path
from els_server.domain.equipment_durability import maximum,validate
from els_server.domain.inventory_items import item_body
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from tests.historical_inventory import seed_existing_items as grant_items
from els_server.storage.equipment_durability import replace_durability
from els_server.storage.attribute_enchant import change_attribute


class DurabilityTests(unittest.TestCase):
    def test_bounds_and_independent_wire_fields(self):
        item=dict(uid=1,template=100,metadata=1,count=1,group=1,slot=0)
        self.assertEqual(maximum(100),10000)
        from els_server.domain.normal_equipment import definitions
        self.assertEqual({maximum(t) for t in definitions()},{10000})
        self.assertEqual(struct.unpack_from('>h',item_body(item),9)[0],0)
        for value in (0,1,2000,10000):
            for attrs in ([0]*4,[1,0,0,0]):
                wire=item_body(dict(item,durability=value,attributes=attrs))
                self.assertEqual(struct.unpack_from('>h',wire,9)[0],value)
                self.assertEqual(len(wire),320 if any(attrs) else 304)
        for value in (-1,10001,32767,True,1.0):
            with self.assertRaises(ValueError):validate(100,value)
        with self.assertRaises(ValueError):validate(77000,10000)

    def test_owned_cas_rollback_restart_and_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters()
            with closing(sqlite3.connect(path)) as db,db:
                self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='equipment_durability'").fetchone())
                gear=grant_items(db,[dict(template=100,metadata=1,quantity=1,group=1)])[0]
                self.assertEqual(gear['durability'],10000)
            with closing(sqlite3.connect(path)) as db:
                with self.assertRaises(ValueError):replace_durability(db,1001,gear['uid'],10000,2000)
                db.execute('BEGIN IMMEDIATE')
                for owner,expected,updated in ((1002,10000,2000),(1001,0,2000),(1001,10000,10001)):
                    with self.assertRaises(ValueError):replace_durability(db,owner,gear['uid'],expected,updated)
                replace_durability(db,1001,gear['uid'],10000,2000);db.rollback()
                self.assertEqual(load_items(db)[0]['durability'],10000)
                db.execute('BEGIN IMMEDIATE');replace_durability(db,1001,gear['uid'],10000,2000);db.commit()
            reloaded=LocalAccount(LocalState(path));reloaded.enable_characters()
            self.assertEqual(reloaded.get_inventory_snapshot()['items'][0]['durability'],2000)
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('DELETE FROM equipment_durability WHERE item_uid=?',(gear['uid'],))
            self.assertNotIn('durability',reloaded.get_inventory_snapshot()['items'][0])
            with closing(sqlite3.connect(path)) as db:
                before=list(db.iterdump())
                try:
                    with db:
                        grant_items(db,[dict(template=30224,metadata=1,quantity=1,group=1)])
                        raise RuntimeError('abort grant')
                except RuntimeError:pass
                self.assertEqual(list(db.iterdump()),before)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_enchant_and_replay_preserve_current_durability(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters()
            with closing(sqlite3.connect(path)) as db,db:
                gear=grant_items(db,[dict(template=100,metadata=1,quantity=1,group=1)])[0]
                grant_items(db,[dict(template=130048,metadata=2,quantity=99,group=4)])
                db.execute('UPDATE reward_balances SET ed=100000000 WHERE uid=1001')
                replace_durability(db,1001,gear['uid'],10000,1999)
            request=struct.pack('>QBB',gear['uid'],0,1)
            for result in (change_attribute(path,1001,request,'durability-enchant'),change_attribute(path,1001,request,'durability-enchant')):
                current=next(i for i in result['inventory'] if i['uid']==gear['uid'])
                self.assertEqual(current['durability'],1999);self.assertEqual(current['attributes'],[1,0,0,0])

if __name__=='__main__':unittest.main()
