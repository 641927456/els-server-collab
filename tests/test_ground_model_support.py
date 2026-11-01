"""Exercise the actual native argument adapter against a bounded JS fixture."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util,subprocess,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'references/registered-ground-items-20261101-v1/source/support/common/tools/native_ground_models.py'

class Snapshot:
    def __getitem__(self,key):return bytes(key.stop-key.start)

class NativeGroundSupportTests(unittest.TestCase):
    def load(self):
        spec=importlib.util.spec_from_file_location('ground_support_candidate',SOURCE);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_unknown_native_identity_is_rejected(self):
        module=self.load()
        with self.assertRaises(ValueError):module.source(b'',module.EXE_SHA)
        with self.assertRaises(ValueError):module.source(b'','wrong')

    def test_actual_adapter_scope_categories_and_failures(self):
        module=self.load()
        # Zero pins belong only to this JS memory fixture. Native identities,
        # caller bytes and114 real loader results are qualified separately.
        with patch.object(module.hashlib,'sha256',return_value=SimpleNamespace(hexdigest=lambda:module.IMAGE_SHA)):
            source=module.source(Snapshot(),module.EXE_SHA)
        with tempfile.TemporaryDirectory(prefix='ground-unit-',dir=ROOT)as directory:
            path=Path(directory)/'source.js';path.write_text(source,encoding='utf8')
            subprocess.run(['node',str(ROOT/'tests/ground_model_support_fixture.js'),str(path)],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()
