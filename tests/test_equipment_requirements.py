import unittest
from els_server.game_data import client_data
from els_server.domain.normal_equipment import definitions
from els_server.domain.equipment_requirements import catalog,class_matches,inspect_requirements

class EquipmentRequirementTests(unittest.TestCase):
    def test_class_route_stage_and_unrestricted_items(self):
        self.assertTrue(class_matches(10,1))
        self.assertFalse(class_matches(1,10))
        self.assertFalse(class_matches(10,11))
        self.assertFalse(class_matches(5,1))
        self.assertTrue(class_matches(5,5))
        for c in catalog()[0]:self.assertTrue(class_matches(c,0))
        for a,b in [(0,0),(1,999),(-1,1),(True,1),(1,True)]:
            with self.assertRaises(ValueError):class_matches(a,b)

    def test_complete_inventory_definition_slot_and_requirement_coverage(self):
        classes,slots=catalog();counts={p:0 for p in slots}
        with client_data().connect() as db:
            for template,position,raw in db.execute('SELECT id,equip_position,record FROM items WHERE item_type IN (1,2)'):
                if template not in definitions():continue
                self.assertIn(position,slots);self.assertIn(raw[0xd3],{0,*classes});counts[position]+=1
        self.assertEqual(counts,{2:10112,8:7569,9:7560,10:7525,11:7838})

    def test_inspection_never_authorizes_wearing(self):
        a=inspect_requirements(100,1);b=inspect_requirements(100,5)
        self.assertTrue(a['class_matches']);self.assertFalse(b['class_matches'])
        self.assertEqual((a['equipment_group'],a['equipment_slot']),(9,9))
        self.assertIs(a['authorizes_equipment_move'],False)
        with self.assertRaises(ValueError):inspect_requirements(77000,1)

if __name__=='__main__':unittest.main()
