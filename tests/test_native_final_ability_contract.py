"""Source integrity and fail-closed host contract; native play is separate."""
from pathlib import Path
import hashlib,importlib.util,json,os,unittest

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'references/native-final-ability-sync-20261027-v1'

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

class NativeFinalAbilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sync=module('native_final_ability_sync',REFERENCE/'tools/native_cache_sync.py')
        cls.contract=module('native_final_ability_compatibility',REFERENCE/'tools/client_compatibility.py')
        cls.registry=json.loads((REFERENCE/'tools/client_compatibility_profiles.json').read_bytes())
        cls.trace=(ROOT/'tools/trace_dx11_login.js').read_text('utf8')

    def test_archive_and_both_variant_dependencies_are_bound(self):
        doc=json.loads((REFERENCE/'candidate.json').read_bytes())
        for row in doc['files']:
            path=(REFERENCE/row['path']).resolve()
            self.assertTrue(path.is_relative_to(REFERENCE.resolve()))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['sha256'])
        for variant,mapping in doc['runtime_variants'].items():
            with self.subTest(variant=variant):
                profile=json.loads((REFERENCE/mapping['tools/client_compatibility_profiles.json']).read_bytes())['profiles'][0]
                for runtime_path,source_path in mapping.items():
                    # The registry is bound by candidate.json above; a digest
                    # inside the same registry cannot bind its own bytes.
                    if runtime_path=='tools/client_compatibility_profiles.json':continue
                    self.assertEqual(profile['artifacts'][runtime_path],hashlib.sha256((REFERENCE/source_path).read_bytes()).hexdigest())

    def test_changed_client_or_image_refused(self):
        for image,exe in [(b'', '0'*64),(b'changed mapped image',self.sync.EXE_SHA)]:
            with self.subTest(executable=exe),self.assertRaisesRegex(ValueError,'client identity'):
                self.sync.compose(image,exe,self.trace)

    def test_missing_native_components_refused_before_launch(self):
        for dependency in ('tools/native_cache_sync.py','tools/native_cache_sync.js'):
            with self.subTest(dependency=dependency):
                registry=json.loads(json.dumps(self.registry))
                registry['profiles'][0]['artifacts'].pop(dependency)
                with self.assertRaisesRegex(ValueError,'Incomplete profile artifact'):
                    self.contract.select(Path('unused-client'),ROOT,registry,executable={'sha256':self.sync.EXE_SHA})

    def test_current_native_composition_and_changed_host_refusal(self):
        path=Path(os.environ.get('ELS_NATIVE_CACHE_IMAGE',str(ROOT/'analysis/client-6c6b5180/x2-runtime.bin')))
        if not path.is_file():self.skipTest('Pinned private mapped image is not provisioned')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=self.sync.IMAGE_SHA:self.skipTest('Provisioned legacy image is outside this client contract')
        code=self.sync.compose(raw,self.sync.EXE_SHA,self.trace)
        self.assertNotIn('__CACHE_SYNC_PINS__',code)
        self.assertNotIn('__CACHE_SYNC_EXE_SHA__',code)
        with self.assertRaisesRegex(ValueError,'parent trace changed'):
            self.sync.compose(raw,self.sync.EXE_SHA,self.trace+'\n// unreviewed host callback\n')

if __name__=='__main__':unittest.main()
