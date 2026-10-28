"""V43 inherits only two exact public self-test source exceptions."""
from pathlib import Path
import importlib.util,unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v43_frozen_guard',ROOT/'tools/repository_guard.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
class V43FrozenPrivacyGuard(unittest.TestCase):
 def test_actual_two_reviewed_sources(self):
  for name in ('Program.cs','ModeDesign.cs'):
   path='launchers/friends-v43/'+name
   self.assertEqual(guard.violations(path,(ROOT/path).read_bytes()),[])
 def test_whole_file_byte_edit_rejected(self):
  for name in ('Program.cs','ModeDesign.cs'):
   path='launchers/friends-v43/'+name
   self.assertIn('literal credential candidate; review required',guard.violations(path,(ROOT/path).read_bytes()+b'\n'))
 def test_other_path_rejected(self):
  for name in ('Program.cs','ModeDesign.cs'):
   data=(ROOT/'launchers/friends-v43'/name).read_bytes()
   self.assertIn('literal credential candidate; review required',guard.violations('launchers/friends-v43/nested/'+name,data))
 def test_real_literal_never_inherits_fixture_exception(self):
  credential=b'pass'+b'word='+b'"'+b'nonfixture-private-value'+b'"'
  for name in ('Program.cs','ModeDesign.cs'):
   path='launchers/friends-v43/'+name
   self.assertIn('literal credential candidate; review required',guard.violations(path,credential))
if __name__=='__main__':unittest.main()
