"""Frozen launcher archives and the two exact random-fixture guard exceptions."""
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('archived_launcher_guard',ROOT/'tools/repository_guard.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)

def snippet(prefix='Fixture-Only-',tail='"+Guid.NewGuid().ToString("N"),name="proof_password";',field='password'):
    return ('string '+field+'="'+prefix+tail).encode()

class LauncherArchive(unittest.TestCase):
    def test_only_exact_random_fixture_is_allowed(self):
        for version in (37,38):
            name='launchers/friends-v'+str(version)+'/Program.cs'
            with self.subTest(version=version):
                self.assertEqual(guard.violations(name,snippet()),[])
                for value in (snippet('fixed-value-for-negative-test'),snippet(tail='";'),snippet(field='token'),snippet(tail='"+Guid.NewGuid().ToString("D"),name="proof_password";'),snippet()+b'\n'+snippet('second-fixed-value')):
                    self.assertIn('literal credential candidate; review required',guard.violations(name,value))
                for other in (name.lower(),name.replace('Program.cs','Other.cs'),name.replace('Program.cs','nested/Program.cs')):
                    self.assertIn('literal credential candidate; review required',guard.violations(other,snippet()))

    def test_private_state_and_keys_remain_blocked(self):
        for version in (37,38):
            home='launchers/friends-v'+str(version)+'/'
            self.assertTrue(guard.violations(home+'accounts.sqlite3',b'{}'))
            self.assertTrue(guard.violations('state/account.json',b'{}'))
            marker=('-----BEGIN '+'PRIVATE KEY-----\n').encode()
            self.assertIn('private key block',guard.violations(home+'key.txt',marker))

    def test_mode_dummy_token_requires_exact_frozen_whole_file(self):
        for version in (37,38):
            name='launchers/friends-v'+str(version)+'/ModeDesign.cs';raw=(ROOT/name).read_bytes()
            self.assertEqual(guard.violations(name,raw),[])
            for changed in (raw+b'\n',raw.replace(b'fixture-token-only',b'changed-token-test'),raw+b'\n'+snippet('second-fixed-value',field='token')):
                self.assertIn('literal credential candidate; review required',guard.violations(name,changed))
            self.assertIn('literal credential candidate; review required',guard.violations(name,snippet('fixture-token-only',field='token')))
            self.assertIn('literal credential candidate; review required',guard.violations(name.replace('ModeDesign.cs','Other.cs'),raw))

    def test_complete_frozen_native_inputs_and_historical_identities(self):
        expected={37:'6349039c19d9d1996ed9ba9abbc3222e5bb61dc9c5a52c6a223f29d7177f919d',38:'0593fbec73b409cd02d368b2dda186fbdf5164c2d8d665c713af50acd7828093'}
        for version,identity in expected.items():
            home=ROOT/'launchers'/('friends-v'+str(version));release=json.loads((home/'release.json').read_bytes())
            self.assertEqual(release['EXE']['sha256'],identity)
            self.assertEqual(hashlib.sha256((home/'source-lock.json').read_bytes()).hexdigest(),release['source_lock_sha256'])
            self.assertIn('Version = '+str(version)+';',(home/'AutoUpdate.cs').read_text('utf-8-sig'))
            self.assertEqual((home/'local_updater.py').exists(),version==38)
            q=subprocess.run([sys.executable,'-B',str(home/'build.py'),'--check-only'],cwd=ROOT,capture_output=True,check=True)
            self.assertTrue(json.loads(q.stdout)['ok'])

if __name__=='__main__':unittest.main()
