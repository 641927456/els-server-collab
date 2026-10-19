import copy,json,unittest
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data
from els_server.domain.normal_equipment import definitions
from els_server.domain.equipment_requirements import catalog as classes_and_slots
from els_server.domain.equipment_eligibility import catalog,inspect_eligibility,validate_proof


class EquipmentEligibilityTests(unittest.TestCase):
    def test_level_family_class_and_blocked_templates(self):
        self.assertTrue(inspect_eligibility(100,1,1)['template_requirements_met'])
        self.assertFalse(inspect_eligibility(100,5,99)['template_requirements_met'])
        self.assertFalse(inspect_eligibility(1000,1,1)['native_template_predicate'])
        self.assertTrue(inspect_eligibility(1000,1,2)['template_requirements_met'])
        self.assertFalse(inspect_eligibility(62110,1,99)['permitted_use_flags'])
        self.assertFalse(inspect_eligibility(62110,1,99)['template_requirements_met'])
        self.assertTrue(inspect_eligibility(28000,5,1)['template_requirements_met'])
        for args in [(100,True,1),(100,0,1),(100,1,0),(100,1,100),(100,1,True),(77000,1,1)]:
            with self.assertRaises(ValueError):inspect_eligibility(*args)

    def test_full_catalog_and_all_common_armor_families(self):
        classes=classes_and_slots()[0];rows=catalog();self.assertEqual(set(rows),set(definitions()))
        self.assertEqual(sum(not r['flags4']&0xf00 for r in rows.values()),215)
        common=[r for r in rows.values() if r['mode']==1]
        self.assertEqual(len(common),1642)
        missing_model=0
        for row in common:
            families={classes[c]['family'] for c,l,a in row['cases']}
            self.assertEqual(families,set(range(1,16)))
            for c,l,a in row['cases']:
                if l<1:continue
                result=inspect_eligibility(row['template'],c,l)
                self.assertEqual(result['native_template_predicate'],bool(a))
                self.assertFalse(result['authorizes_equipment_move'])
                if not row['generic_model'] and not row['models'][str(classes[c]['family'])]:missing_model+=1
        self.assertGreater(missing_model,0)

    def test_evidence_rejects_boundary_gap_and_resource_tampering(self):
        manifest=json.loads((PROJECT_ROOT/'els_server/data/equipment_eligibility.manifest.json').read_text())
        full=json.loads((PROJECT_ROOT/manifest['proof']).read_text());row=next(r for r in full['rows'] if r['mode']==1)
        proof=dict(full,rows=[row],count=1,case_count=len(row['cases']));manifest=dict(manifest,count=1,case_count=len(row['cases']))
        records={row['template']:client_data().item(row['template'])['record']}
        self.assertEqual(len(validate_proof(manifest,proof,records)),1)
        for field,value in [('flags4',row['flags4']^0x100),('level',255),('models',{}),('cases',row['cases'][:-1])]:
            bad=copy.deepcopy(proof);bad['rows'][0][field]=value
            with self.assertRaises(ValueError):validate_proof(manifest,bad,records)
        bad=copy.deepcopy(proof);bad['rows'][0]['cases'][0][2]^=1
        with self.assertRaises(ValueError):validate_proof(manifest,bad,records)
        with self.assertRaises(ValueError):validate_proof(manifest,proof,{row['template']:bytes(232)})

if __name__=='__main__':unittest.main()
