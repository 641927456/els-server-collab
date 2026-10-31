"""Portable checks for the exact dual-mode signed login repair sources."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / 'references/native-login-reconnect-20261031-v1'


class LoginReconnectSupportTests(unittest.TestCase):
    def test_all_declared_sources_match(self):
        contract = json.loads((REF / 'source-contract.json').read_bytes())
        for row in contract['files']:
            raw = (REF / row['path']).read_bytes()
            self.assertEqual(len(raw), row['size'], row['path'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'], row['path'])
        self.assertEqual(contract['new_native_Hooks'], 0)
        self.assertEqual(contract['original_EXE_KOM_changes'], 0)

    def test_compositor_pins_both_mode_specific_traces(self):
        source = (REF / 'source/shared/tools/native_cache_sync.py').read_text('utf8')
        tree = ast.parse(source)
        node = next(n for n in tree.body if isinstance(n, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id == 'TRACE_TEXT_SHAS' for t in n.targets))
        allowed = set(ast.literal_eval(node.value.args[0]))
        for mode in ('friends', 'signed-local', 'raw-local'):
            text = (REF / 'source' / mode / 'tools/trace_dx11_login.js').read_text('utf8')
            self.assertIn(hashlib.sha256(text.encode()).hexdigest(), allowed)
            self.assertNotIn(hashlib.sha256((text + '\n// drift').encode()).hexdigest(), allowed)
        for mode in ('friends', 'signed-local'):
            profile = json.loads((REF / 'source' / mode / 'tools/client_compatibility_profiles.json').read_bytes())
            entry = next(p for p in profile['profiles'] if p['id'] == 'cn-dx11-6c6b5180')
            cache = (REF / 'source/shared/tools/native_cache_sync.py').read_bytes()
            trace = (REF / 'source' / mode / 'tools/trace_dx11_login.js').read_bytes()
            self.assertEqual(entry['artifacts']['tools/native_cache_sync.py'], hashlib.sha256(cache).hexdigest())
            self.assertEqual(entry['artifacts']['tools/trace_dx11_login.js'], hashlib.sha256(trace).hexdigest())

    def test_observed_reconnect_does_not_inject_selection(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node is required for the actual JS callback replay')
        for mode in ('friends', 'signed-local'):
            result = subprocess.run([node, str(REF / 'test_entry.cjs'),
                                     str(REF / 'source/parents' / mode / 'trace_dx11_login.js'),
                                     str(REF / 'source' / mode / 'tools/trace_dx11_login.js')],
                                    capture_output=True, timeout=30, check=True)
            proof = json.loads(result.stdout)
            self.assertTrue(proof['passed'])
            self.assertEqual(proof['interactiveReconnectCalls'], 0)
            self.assertEqual(proof['isolatedProbeCallsRetained'], 2)

    def test_delivery_boundaries_are_explicit(self):
        evidence = json.loads((REF / 'installation-evidence.json').read_bytes())
        self.assertTrue(evidence['LOCAL']['installed'])
        self.assertTrue(evidence['Friends']['public_signed_components_verified'])
        self.assertTrue(evidence['signed_LOCAL']['actual_CSharp_upgrade_and_repeat'])
        self.assertFalse(evidence['natural_player_login_verified'])
        self.assertFalse(evidence['main_merged'])


if __name__ == '__main__':
    unittest.main()
