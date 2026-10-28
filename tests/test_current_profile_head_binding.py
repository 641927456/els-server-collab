"""A valid-looking digest cannot replace an accepted installation head."""
from pathlib import Path
import copy,json,tempfile,unittest
from tools.materialize_formal_runtime import load_manifest
ROOT=Path(__file__).resolve().parents[1]

class AcceptedHeadBindingTests(unittest.TestCase):
    def setUp(self):
        cache=ROOT/'.runtime-cache';cache.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='head-binding-',dir=cache)
        self.base=Path(self.tmp.name).resolve();self.assertEqual(self.base.parent,cache.resolve())
        self.addCleanup(self.tmp.cleanup)
        heads={c:dict(release='controlled-'+c,formal_manifest_sha256=ch*64)for c,ch in (('online','a'),('local','b'))}
        self.profile=dict(candidate=False,actual_dual_delivery_verified=True,accepted_heads=heads,channels={c:dict(files=[])for c in heads})
        self.pointer=dict(format=1,profile='profile.json',accepted=copy.deepcopy(heads))

    def load(self):
        for name,value in (('profile.json',self.profile),('current.json',self.pointer)):
            (self.base/name).write_text(json.dumps(value),encoding='utf-8')
        return load_manifest(self.base/'current.json',self.base)

    def test_exact_accepted_heads_load(self):
        self.assertEqual(self.load()['channels']['local']['release'],'controlled-local')

    def test_wrong_but_well_formed_manifest_digest_rejected(self):
        self.pointer['accepted']['local']['formal_manifest_sha256']='c'*64
        with self.assertRaisesRegex(ValueError,'accepted profile'):self.load()

    def test_uninstalled_candidate_cannot_claim_accepted_heads(self):
        self.profile['candidate']=True
        with self.assertRaisesRegex(ValueError,'accepted profile'):self.load()

if __name__=='__main__':unittest.main()
