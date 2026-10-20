"""V32 source identity and narrow privacy exception, without launching anything."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'launchers/friends-v31'
NEW=ROOT/'launchers/friends-v32'
spec=importlib.util.spec_from_file_location('v32_repository_guard',ROOT/'tools/repository_guard.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)


class V32Sources(unittest.TestCase):
    def test_exact_two_shell_literal_changes(self):
        release=json.loads((NEW/'release.json').read_bytes())
        before=json.loads((OLD/'release.json').read_bytes())
        self.assertEqual((OLD/'Program.cs').read_bytes().replace(before['runtime_sha256'].encode(),release['runtime_sha256'].encode()),(NEW/'Program.cs').read_bytes())
        self.assertEqual((OLD/'AutoUpdate.cs').read_bytes().replace(b'public const int Version = 31;',b'public const int Version = 32;'),(NEW/'AutoUpdate.cs').read_bytes())
        for old in OLD.glob('*.cs'):
            if old.name not in ('Program.cs','AutoUpdate.cs'):self.assertEqual(old.read_bytes(),(NEW/old.name).read_bytes())
        self.assertEqual((OLD/'build-assets.lock.json').read_bytes(),(NEW/'build-assets.lock.json').read_bytes())
        self.assertEqual((OLD/'app.manifest').read_bytes(),(NEW/'app.manifest').read_bytes())
    def test_signed_manifest_and_three_exact_support_modules(self):
        release=json.loads((NEW/'release.json').read_bytes())
        raw=(NEW/'runtime-files.signed.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),release['signed_manifest_sha256'])
        envelope=json.loads(raw);doc=json.loads(base64.b64decode(envelope['payload']))
        self.assertEqual(doc['archive']['sha256'],release['runtime_sha256'])
        self.assertEqual(len(doc['files']),1082)
        manifest={r['path']:r for r in doc['files']}
        self.assertEqual(len(release['runtime_support_delta']),3)
        old_doc=json.loads(base64.b64decode(json.loads((OLD/'runtime-files.signed.json').read_bytes())['payload']))
        old_manifest={r['path']:r for r in old_doc['files']}
        self.assertEqual(set(manifest),set(old_manifest))
        self.assertEqual({n for n in manifest if manifest[n]!=old_manifest[n]},
                         {r['path'] for r in release['runtime_support_delta']})
        self.assertEqual(sum(manifest[n]==old_manifest[n] for n in manifest),1079)
        for row in release['runtime_support_delta']:
            raw=(NEW/'runtime-support'/row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
            self.assertEqual(len(raw),row['size'])
            self.assertEqual(manifest[row['path']]['sha256'],row['sha256'])
    def test_random_fixture_is_only_allowed_at_exact_path_and_context(self):
        # Compose the synthetic field name so this test does not itself look
        # like a stored credential to the repository upload guard.
        text=('string pass'+'word="Fixture-Only-"+Guid.NewGuid().ToString("N"),name="proof_password";').encode()
        self.assertEqual(guard.violations('launchers/friends-v32/Program.cs',text),[])
        self.assertTrue(guard.violations('launchers/friends-v32/Other.cs',text))
        self.assertTrue(guard.violations('launchers/friends-v33/Program.cs',text))
        self.assertTrue(guard.violations('launchers/friends-v32/Program.cs',text.replace(b'Guid.NewGuid()',b'Guid.Empty')))
        self.assertTrue(guard.violations('launchers/friends-v32/Program.cs',text.replace(b'Fixture-Only-',b'Unapproved-Literal-')))
    def test_other_credential_literals_still_fail(self):
        text=('string to'+'ken="not-a-real-secret-fixture";').encode()
        self.assertTrue(guard.violations('launchers/friends-v32/Program.cs',text))


if __name__=='__main__':unittest.main()
