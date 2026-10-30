"""Compare server instance computation with native outputs, not copied formulas."""
import json,struct,unittest
from pathlib import Path
from els_server.domain.instance_stats import normal_instance_attributes,catalog
from els_server.domain.character_stats import equipment_attributes,combat_values,combat_attributes

PROOF=Path(__file__).resolve().parents[1]/'analysis/integration-20261015'
CHARACTER=dict(unit_class=100,unit_type=1,level=40)


class InstanceStatsTests(unittest.TestCase):
    def test_all_default_normal_templates_against_native(self):
        proof=json.loads((PROOF/'instance-stat-bonuses-native.json').read_text())
        self.assertEqual(len(proof['rows']),catalog()['normal_template_count'])
        for row in proof['rows']:
            self.assertEqual(list(normal_instance_attributes(row['template'],CHARACTER)),row['result'][6:],row['template'])

    def test_enhancement_and_both_mode_matrices(self):
        proof=json.loads((PROOF/'instance-stat-matrix-native.json').read_text())
        cases=0
        for row in proof['rows']:
            for case in row['matrixCases']:
                cases+=1
                self.assertEqual(list(normal_instance_attributes(row['template'],CHARACTER,enhancement=case['level'],mode=case['mode'])),case['result'][6:],(row['template'],case['level'],case['mode']))
        self.assertEqual(cases,5208)

    def test_instance_effects_enter_estimate_without_double_sending_base(self):
        item=dict(uid=10,template=30388,metadata=1,count=1,group=9,slot=9,durability=10000)
        raw=equipment_attributes(item['template'],CHARACTER)
        native=normal_instance_attributes(item['template'],CHARACTER)
        self.assertEqual(raw[1:3],(7242,5537))
        self.assertEqual(native[1:3],(7902,6047))
        self.assertEqual(combat_values(CHARACTER,[item])[1:3],(8573,6718))
        self.assertEqual(struct.unpack('>7f',combat_attributes(CHARACTER,[item])),combat_values(CHARACTER))
        for bad in (-1,21,True,1.5):
            with self.assertRaises(ValueError):normal_instance_attributes(30388,CHARACTER,enhancement=bad)
        for bad in (-1,2,True):
            with self.assertRaises(ValueError):normal_instance_attributes(30388,CHARACTER,mode=bad)
        with self.assertRaises(ValueError):normal_instance_attributes(77000,CHARACTER)

    def test_private_owner_levels_with_fresh_native_cache(self):
        proof=json.loads((PROOF/'instance-stat-levels-native.json').read_text())
        self.assertTrue(proof['complete']['derivedCacheClearedPerContext'])
        self.assertFalse(proof['live_owner_writes'])
        cases=0
        for row in proof['rows']:
            for case in row['matrixCases']:
                cases+=1
                character=dict(CHARACTER,level=case['owner_level'])
                self.assertEqual(list(normal_instance_attributes(row['template'],character,enhancement=case['level'],mode=case['mode'])),case['result'][6:],(row['template'],case['owner_level'],case['level'],case['mode']))
        self.assertEqual(cases,3968)


if __name__=='__main__':unittest.main()
