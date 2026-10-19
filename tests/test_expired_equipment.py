import unittest
from unittest.mock import patch
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
from els_server.domain.character_stats import combat_values,equipment_contributes
from els_server.domain.equipment_instance import require_wearable,contributes_attributes


class ExpiredEquipmentTests(unittest.TestCase):
    def test_deadline_boundary_and_stale_inventory_stat_contributions(self):
        character=dict(unit_class=100,unit_type=1,level=40)
        deadline=1792056000
        weapon=dict(uid=1,template=60100,metadata=1,count=1,group=9,slot=9,durability=10000,expires_at=deadline)
        fashion=dict(uid=2,template=81021,metadata=0,count=1,group=9,slot=FASHION_EQUIP_SLOTS[81021],expires_at=deadline)
        base=combat_values(character)
        with patch('time.time',return_value=deadline):
            self.assertTrue(contributes_attributes(weapon,character))
            self.assertTrue(equipment_contributes(fashion,character))
            self.assertNotEqual(combat_values(character,[weapon]),base)
            require_wearable(weapon,character)
        with patch('time.time',return_value=deadline+1):
            self.assertFalse(contributes_attributes(weapon,character))
            self.assertFalse(equipment_contributes(weapon,character))
            self.assertFalse(equipment_contributes(fashion,character))
            self.assertEqual(combat_values(character,[weapon]),base)
            with self.assertRaises(ValueError):require_wearable(weapon,character)
