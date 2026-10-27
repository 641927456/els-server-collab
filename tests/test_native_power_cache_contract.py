"""Fail-closed contract checks; private native execution is separately qualified."""
from pathlib import Path
import hashlib,importlib.util,json,os,unittest

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'references/native-power-cache-sync-20261027-v1/tools'

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

class NativePowerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sync=module('candidate_native_power_sync',REFERENCE/'native_cache_sync.py')
        cls.contract=module('candidate_native_power_contract',REFERENCE/'client_compatibility.py')
        cls.registry=json.loads((REFERENCE/'client_compatibility_profiles.json').read_bytes())
        cls.trace=(ROOT/'tools/trace_dx11_login.js').read_text('utf8')

    def current_image(self):
        image=Path(os.environ.get('ELS_NATIVE_CACHE_IMAGE',str(ROOT/'analysis/client-6c6b5180/x2-runtime.bin')))
        if not image.is_file():self.skipTest('Current private mapped image is not provisioned')
        raw=image.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=self.sync.IMAGE_SHA:
            self.skipTest('Provisioned legacy image is outside the current native cache contract')
        return raw

    def test_unknown_executable_and_changed_image_refused(self):
        with self.assertRaisesRegex(ValueError,'client identity'):
            self.sync.compose(b'', '0'*64, self.trace)
        with self.assertRaisesRegex(ValueError,'client identity'):
            self.sync.compose(b'changed mapped image',self.sync.EXE_SHA,self.trace)

    def test_missing_synchronizer_dependency_refused_before_artifact_reads(self):
        for dependency in ('tools/native_cache_sync.py','tools/native_cache_sync.js'):
            with self.subTest(dependency=dependency):
                registry=json.loads(json.dumps(self.registry))
                registry['profiles'][0]['artifacts'].pop(dependency)
                with self.assertRaisesRegex(ValueError,'Incomplete profile artifact'):
                    self.contract.select(Path('unused-client'),ROOT,registry,
                        executable={'sha256':self.sync.EXE_SHA})

    def test_unknown_profile_refused(self):
        with self.assertRaises(self.contract.CompatibilityPending):
            self.contract.select(Path('unused-client'),ROOT,self.registry,
                executable={'sha256':'0'*64})

    def test_changed_host_trace_requires_explicit_merge(self):
        raw=self.current_image()
        with self.assertRaisesRegex(ValueError,'parent trace changed'):
            self.sync.compose(raw,self.sync.EXE_SHA,self.trace+'\n// changed host callback\n')

if __name__=='__main__':unittest.main()
