"""Route changes retain gear, disable incompatible stats, and survive replay."""
import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.equipment_moves import move_equipment
from els_server.storage.careers import use_career_item
from els_server.domain.character_stats import combat_values,combat_breakdown,equipment_attributes
from els_server.domain.equipment_instance import contributes_attributes
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS


class CareerEquipmentTests(unittest.TestCase):
    def test_cross_route_retains_uid_and_disables_then_restores_contribution(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite3';a=LocalAccount(LocalState(path));a.enable_characters()
            with closing(sqlite3.connect(path)) as db,db:
                db.execute('UPDATE characters SET unit_class=100,level=40 WHERE uid=1001')
                gear,outward,returning=[grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],quantity=1,group=TEMPLATE_BAG_GROUPS[t])])[0] for t in (60100,242140,242130)]
            move_equipment(path,struct.pack('>BiBiB',1,gear['slot'],9,9,0))
            def owned():
                with closing(sqlite3.connect(path)) as db:return next(i for i in load_items(db) if i['uid']==gear['uid'])
            original=owned();c=a.character();self.assertTrue(contributes_attributes(original,c))
            before=combat_values(c,[original]);self.assertNotEqual(before,combat_values(c))
            for ticket,wanted,active in ((outward,101,False),(returning,100,True)):
                payload=struct.pack('>QQiiIB',ticket['uid'],0,0,0,0,0);identity='cross-route-'+str(wanted)
                self.assertFalse(use_career_item(path,1001,payload,identity)['replayed'])
                self.assertTrue(use_career_item(path,1001,payload,identity)['replayed'])
                reopened=LocalAccount(LocalState(path));reopened.enable_characters();c=reopened.character()
                self.assertEqual(c['unit_class'],wanted);self.assertEqual(owned(),original)
                self.assertEqual(contributes_attributes(original,c),active)
                self.assertEqual(combat_breakdown(c,[original])['equipment'][0]['contributes'],active)
                self.assertEqual(combat_values(c,[original]),before if active else combat_values(c))
            # Unwear remains possible even while the route requirement fails.
            with closing(sqlite3.connect(path)) as db,db:db.execute('UPDATE characters SET unit_class=101 WHERE uid=1001')
            move_equipment(path,struct.pack('>BiBiB',9,9,1,gear['slot'],0))
            with self.assertRaises(ValueError):move_equipment(path,struct.pack('>BiBiB',1,gear['slot'],9,9,0))
            self.assertEqual(owned()['group'],1)

    def test_normal_effect_durability_and_class_filter_is_not_wear_permission(self):
        c=dict(unit_class=100,unit_type=1,level=40)
        item=dict(uid=10,template=60100,metadata=1,count=1,group=9,slot=9,durability=10000)
        self.assertTrue(contributes_attributes(item,c))
        self.assertTrue(contributes_attributes(item,dict(c,level=1))) # no level recheck in 8A20E0
        for changed in (dict(item,durability=0),{k:v for k,v in item.items() if k!='durability'},dict(item,group=1,slot=0)):
            self.assertFalse(contributes_attributes(changed,c));self.assertEqual(combat_values(c,[changed]),combat_values(c))
        for cls in (101,102,103,11,200,205):self.assertFalse(contributes_attributes(item,dict(c,unit_class=cls)))
        for cls in (100,150):self.assertTrue(contributes_attributes(item,dict(c,unit_class=cls)))

if __name__=='__main__':unittest.main()
