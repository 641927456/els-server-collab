"""The future profile cannot inherit structural acceptance without its receipt."""
from pathlib import Path
import copy,json,unittest
from unittest.mock import patch
import tools.verify_shared_repair_inheritance_20261030 as inheritance
from tools.verify_shared_repair_inheritance_20261030 import source_contract,verified_shared_repair_predecessor
ROOT=Path(__file__).resolve().parents[1]
class SharedRepairInheritance(unittest.TestCase):
    def test_exact_source31_inventory_has_no_acceptance(self):
        contract,candidate,parent=source_contract(ROOT)
        self.assertFalse(candidate['actual_dual_delivery_verified'])
        self.assertTrue(candidate['candidate'])
        self.assertEqual(contract['business_files'],{'online':1315,'local':1340})
    def test_structure_parent_passes_through_unchanged(self):
        _,_,parent=source_contract(ROOT)
        row=next(r for r in parent['channels']['local']['files']if r['path']=='els_server/storage/seal_quests.py')
        path=ROOT/row['source']
        actual=verified_shared_repair_predecessor(parent,'local',row,path,root=ROOT)
        self.assertEqual(actual,(parent,row,path))
    def test_candidate_cannot_use_future_accepted_name(self):
        _,candidate,_=source_contract(ROOT)
        profile=copy.deepcopy(candidate);profile['name']='native-shared-repair-accepted-20261030-v1'
        row=next(r for r in profile['channels']['local']['files']if r['path']=='els_server/storage/seal_quests.py')
        with self.assertRaises(AssertionError):
            verified_shared_repair_predecessor(profile,'local',row,ROOT/row['source'],root=ROOT)
    def test_no_accepted_profile_is_changed_by_source_check(self):
        profile=ROOT/'channels/native-shared-repair-accepted-20261030-v1.json'
        before=profile.read_bytes()if profile.exists()else None
        source_contract(ROOT)
        self.assertEqual(profile.read_bytes()if profile.exists()else None,before)
    def test_future_flags_do_not_replace_a_real_receipt(self):
        contract,candidate,_=source_contract(ROOT)
        prospective=copy.deepcopy(candidate)
        prospective.update(name='native-shared-repair-accepted-20261030-v1',candidate=False,actual_dual_delivery_verified=True,accepted_heads=contract['accepted_heads'],accepted_delivery=inheritance.REF+'/accepted-delivery.json')
        row=next(r for r in prospective['channels']['local']['files']if r['path']=='els_server/storage/seal_quests.py')
        original_read,original_sha=inheritance.read,inheritance.sha
        def fixture_read(path):
            if path==ROOT/inheritance.ACCEPTED:return prospective
            if path==ROOT/inheritance.REF/'accepted-delivery.json':raise FileNotFoundError('Explicit missing receipt fixture')
            return original_read(path)
        def fixture_sha(path):
            if path==ROOT/inheritance.ACCEPTED:return contract['prospective_accepted_profile_sha256']
            return original_sha(path)
        with patch.object(inheritance,'read',fixture_read),patch.object(inheritance,'sha',fixture_sha):
            with self.assertRaises((AssertionError,FileNotFoundError)):
                verified_shared_repair_predecessor(prospective,'local',row,ROOT/row['source'],root=ROOT)
if __name__=='__main__':unittest.main()
