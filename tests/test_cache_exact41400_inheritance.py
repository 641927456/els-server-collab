"""Reject expanded scope and invented acceptance; test fixtures stay in memory."""
from pathlib import Path
import copy,json,unittest
from tools.verify_cache_exact41400_inheritance_20261030 import (REF,PARENT,CANDIDATE,validate_delta,accepted_document,require_receipts)
ROOT=Path(__file__).resolve().parents[1]
class ExactTwoInheritance(unittest.TestCase):
    def data(self):
        return tuple(json.loads((ROOT/p).read_bytes())for p in(PARENT,CANDIDATE,REF+'/source-contract.json'))
    def test_actual_frozen_candidate_has_exact_two_deltas(self):
        self.assertTrue(validate_delta(*self.data()))
    def test_third_leaf_rejected(self):
        parent,candidate,contract=self.data();candidate['channels']['local']['files'][0]['sha256']='0'*64
        with self.assertRaises(AssertionError):validate_delta(parent,candidate,contract)
    def test_top_level_locator_cannot_replace_archive(self):
        parent,candidate,contract=self.data()
        row=next(r for r in candidate['channels']['online']['files']if r['path']=='els_server/domain/raid_reward_items.py');row['source']=row['path']
        next(r for r in contract['changes']['online']if r['path']==row['path'])['after']=copy.deepcopy(row)
        with self.assertRaises(AssertionError):validate_delta(parent,candidate,contract)
    def test_candidate_flags_do_not_confer_acceptance(self):
        parent,candidate,contract=self.data();candidate['actual_dual_delivery_verified']=True
        with self.assertRaises(AssertionError):validate_delta(parent,candidate,contract)
    def test_duplicate_local_path_rejected(self):
        parent,candidate,contract=self.data();candidate['channels']['local']['files'].append(copy.deepcopy(candidate['channels']['local']['files'][0]))
        with self.assertRaises(AssertionError):validate_delta(parent,candidate,contract)
    def test_missing_real_receipt_rejected(self):
        _,candidate,contract=self.data()
        with self.assertRaises(KeyError):require_receipts(accepted_document(candidate),candidate,contract,{})
    def test_synthetic_receipt_rejected(self):
        _,candidate,contract=self.data();fake=dict(ok=True,actual_dual_delivery_verified=True,synthetic_fixture=True)
        with self.assertRaises(AssertionError):require_receipts(accepted_document(candidate),candidate,contract,fake)
    def test_deterministic_profile_has_no_launcher_self_reference(self):
        _,candidate,_=self.data();profile=accepted_document(candidate)
        self.assertEqual(profile,accepted_document(candidate));self.assertNotIn('launcher',json.dumps(profile).split('"channels"',1)[0])
        self.assertTrue(candidate['candidate']);self.assertFalse(candidate['actual_dual_delivery_verified'])
if __name__=='__main__':unittest.main()
