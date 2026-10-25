"""Fixed archive pins remain independent from bytes measured at runtime."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from tools import dx11_resource_compat as target

ROOT = Path(__file__).resolve().parents[1]


class FixedResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'tools').mkdir()
        self.client = self.root/'data'
        self.client.mkdir()
        (self.client/'x2_dx11.exe').write_bytes(b'exact client fixture')
        entries=[]
        for name in ('data002.kom', 'data275.kom'):
            raw=('fixed archive '+name).encode()
            (self.client/name).write_bytes(raw)
            entries.append(dict(file=name,size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                                original_digest='A'*40,local_digest='B'*40))
        self.spec=dict(client_sha256=hashlib.sha256(b'exact client fixture').hexdigest(),
                       entries=entries,compatibility=entries[1:])
        (self.root/'tools/dx11_resource_compat.json').write_text(json.dumps(self.spec),encoding='utf8')
        (self.root/'tools/dx11_resource_compat.js').write_bytes((ROOT/'tools/dx11_resource_compat.js').read_bytes())

    def build(self, **kwargs):
        # Only isolate the large runtime-image contract; disk SHA256 pins and
        # file_digest are real and the unknown-image rejection is tested below.
        expected=NS(hexdigest=lambda:'3cc9fca449c7a543957c5cdf439c7ba81323efd4a4b3fe577ed0ff0e954a820a')
        with patch.object(target,'ROOT',self.root),patch.object(target.hashlib,'sha256',return_value=expected):
            return target.resource_compat_source(bytes(16),self.client,**kwargs)

    def test_fixed_profile_checks_all_archives_including_nonlegacy_entry(self):
        self.assertIn('const riPinnedProfile=true',self.build())
        (self.client/'data002.kom').write_bytes(b'changed archive')
        with self.assertRaisesRegex(ValueError,'data002.kom differs'):
            self.build()

    def test_explicit_fixed_profile_rejects_different_executable(self):
        (self.client/'x2_dx11.exe').write_bytes(b'other client')
        with self.assertRaisesRegex(ValueError,'exact witnessed client'):
            self.build(use_pinned_profile=True)

    def test_variant_uses_only_preverified_legacy_compatibility(self):
        (self.client/'x2_dx11.exe').write_bytes(b'other client')
        self.assertIn('const riPinnedProfile=false',self.build())
        (self.client/'data275.kom').write_bytes(b'changed archive')
        with self.assertRaisesRegex(ValueError,'data275.kom differs'):
            self.build()

    def test_unknown_runtime_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unverified resource-checking client image'):
            target.resource_compat_source(b'unknown runtime',self.client)

    @unittest.skipUnless(shutil.which('node'),'Node is needed for controlled Frida callbacks')
    def test_actual_callbacks_never_learn_measured_digest(self):
        result=subprocess.run([shutil.which('node'),str(ROOT/'tests/pr480_integrity_harness.js'),
                               str(ROOT/'tools/dx11_resource_compat.js')],check=True,
                              capture_output=True,text=True)
        rows=json.loads(result.stdout)
        self.assertTrue(rows['fixed']['nativePass'])
        self.assertTrue(rows['fixed']['independentMatch'])
        self.assertTrue(rows['legacyAccepted']['nativePass'])
        for name in ('tampered','unknown','legacyUnknownExpected'):
            self.assertFalse(rows[name]['nativePass'],name)
            self.assertFalse(rows[name]['learnedMeasuredDigest'],name)
        self.assertFalse(rows['tampered']['independentMatch'])


if __name__ == '__main__':
    unittest.main()
