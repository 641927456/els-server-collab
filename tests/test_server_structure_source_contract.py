"""Exact extraction identities never authorize unknown bytes or deployment."""
import copy,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools import verify_server_structure_20261029 as verify

class StructuralSuccessor(unittest.TestCase):
    def setUp(self):
        cache=verify.ROOT/'.runtime-cache';cache.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='structure-source-',dir=cache);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);original=verify.ROOT;folder=original/'references'/verify.RID
        self.delta=verify.read(folder/'delta.json')
        names=[folder/'delta.json',folder/'qualification.json',folder/'projection-inverse.json',
               original/self.delta['parent'],original/self.delta['candidate_profile']]
        self.profile=verify.read(original/self.delta['candidate_profile'])
        for mode in ('online','local'):
            rows=verify.files(self.profile,mode)
            names.extend(original/rows[k]['source']for k in (verify.PROJECTION,verify.HELPER))
            names.append(original/self.delta['channels'][mode][verify.PROJECTION]['before_source'])
        for source in names:
            dest=self.root/source.relative_to(original);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        self.addCleanup(patch.stopall)
        patch.object(verify,'ROOT',self.root).start();patch.object(verify,'F',self.root/'references'/verify.RID).start()
        self.entry=verify.files(self.profile,'online')[verify.PROJECTION]
        self.path=self.root/self.entry['source']

    def test_exact_both_channel_extractions_restore_owned_parent(self):
        for mode in ('online','local'):
            entry=verify.files(self.profile,mode)[verify.PROJECTION]
            prior,path=verify.candidate_predecessor(mode,entry,self.root/entry['source'])
            self.assertEqual(prior['sha256'],self.delta['channels'][mode][verify.PROJECTION]['before_sha256'])
            self.assertEqual(verify.sha(path.read_bytes()),prior['sha256'])

    def test_changed_source_bytes_rejected(self):
        self.path.write_bytes(self.path.read_bytes()+b'\n# changed\n')
        with self.assertRaises(AssertionError):verify.candidate_predecessor('online',self.entry,self.path)

    def test_equal_bytes_at_unqualified_location_rejected(self):
        elsewhere=self.root/'equal.py';elsewhere.write_bytes(self.path.read_bytes())
        with self.assertRaises(AssertionError):verify.candidate_predecessor('online',self.entry,elsewhere)
        with self.assertRaises(AssertionError):verify.candidate_predecessor('online',dict(self.entry,source='equal.py'),elsewhere)

    def test_wrong_digest_does_not_gain_candidate_qualification(self):
        unknown=dict(self.entry,sha256='0'*64)
        with self.assertRaises(AssertionError):verify.candidate_predecessor('online',unknown,self.path)
        self.assertEqual(verify.verified_structure_predecessor(self.profile,'online',unknown,self.path),(unknown,self.path))

    def test_changed_helper_rejected(self):
        row=verify.files(self.profile,'online')[verify.HELPER];path=self.root/row['source']
        path.write_bytes(path.read_bytes()+b'\n# changed\n')
        with self.assertRaises(AssertionError):verify.candidate_predecessor('online',self.entry,self.path)

    def test_changed_inverse_rejected(self):
        path=verify.F/'projection-inverse.json';path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(AssertionError):verify.candidate_predecessor('online',self.entry,self.path)

    def test_uninstalled_candidate_cannot_enter_live_successor_chain(self):
        with self.assertRaisesRegex(AssertionError,'Uninstalled'):verify.verified_structure_predecessor(self.profile,'online',self.entry,self.path)

    def test_claimed_flags_without_actual_acceptance_are_rejected(self):
        claimed=copy.deepcopy(self.profile);claimed.update(candidate=False,actual_dual_delivery_verified=True)
        with self.assertRaises(FileNotFoundError):verify.verified_structure_predecessor(claimed,'online',self.entry,self.path)

if __name__=='__main__':unittest.main()
