"""Frozen public self-test exceptions and the exact V45 background boundary."""
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
class V45FrozenPrivacyGuard(unittest.TestCase):
 def test_actual_reviewed_build_inputs(self):
  for name in ('Program.cs','ModeDesign.cs','assets/ruben.png'):
   path='launchers/friends-v45/'+name
   self.assertEqual(guard.violations(path,(ROOT/path).read_bytes()),[])
 def test_changed_bytes_and_unreviewed_paths_rejected(self):
  for name in ('Program.cs','ModeDesign.cs','assets/ruben.png'):
   path='launchers/friends-v45/'+name;data=(ROOT/path).read_bytes()
   self.assertTrue(guard.violations(path,data+b'\n'))
   self.assertTrue(guard.violations('launchers/friends-v45/nested/'+name,data))
 def test_fixture_exception_does_not_admit_other_credentials(self):
  credential=b'pass'+b'word='+b'"'+b'nonfixture-private-value'+b'"'
  for name in ('Program.cs','ModeDesign.cs'):
   path='launchers/friends-v45/'+name
   self.assertIn('literal credential candidate; review required',guard.violations(path,credential))
 def test_other_binary_and_private_paths_still_rejected(self):
  image=(ROOT/'launchers/friends-v45/assets/ruben.png').read_bytes()
  for path in ('launchers/friends-v46/assets/ruben.png','analysis/ruben.png','launchers/friends-v45/assets/ruben.exe'):
   self.assertTrue(guard.violations(path,image))
  self.assertTrue(guard.violations('launchers/friends-v45/assets/ruben.png',b'\x89PNG\r\n\x1a\n\0unreviewed'))
if __name__=='__main__':unittest.main()
