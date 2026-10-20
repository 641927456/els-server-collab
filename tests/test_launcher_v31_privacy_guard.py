"""The launcher random-fixture exception is limited to exact source/context."""
from pathlib import Path
import importlib.util,unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('launcher_fixture_guard',ROOT/'tools/repository_guard.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)

def snippet(prefix='Fixture-Only-',tail='"+Guid.NewGuid().ToString("N"),name="proof_password";',field='password'):
    return ('string '+field+'="'+prefix+tail).encode()

class LauncherV31PrivacyGuard(unittest.TestCase):
    def test_only_exact_two_program_paths_allow_generated_fixture(self):
        for version in ('29','31'):
            self.assertEqual(guard.violations('launchers/friends-v'+version+'/Program.cs',snippet()),[])
        for name in ('Program.cs','launchers/friends-v31/Other.cs','launchers/friends-v31/nested/Program.cs','launchers/friends-v32/Program.cs','launchers/friends-v31/program.cs'):
            self.assertIn('literal credential candidate; review required',guard.violations(name,snippet()))

    def test_fixed_values_and_other_fields_remain_blocked(self):
        name='launchers/friends-v31/Program.cs'
        for value in (snippet('different-fixture-'),snippet(tail='";'),snippet(tail='"+Guid.NewGuid().ToString("D"),name="proof_password";'),snippet(field='token')):
            self.assertIn('literal credential candidate; review required',guard.violations(name,value))
        combined=snippet()+b'\n'+snippet('another-fixed-value')
        self.assertIn('literal credential candidate; review required',guard.violations(name,combined))

    def test_private_paths_and_key_blocks_still_fail(self):
        self.assertTrue(guard.violations('state/account.json',b'{}'))
        self.assertTrue(guard.violations('launchers/friends-v31/profile.sqlite3',b'{}'))
        key_marker=('-----BEGIN '+'PRIVATE KEY-----\n').encode()
        self.assertIn('private key block',guard.violations('launchers/friends-v31/key.txt',key_marker))

if __name__=='__main__':unittest.main()
