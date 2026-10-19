"""Challenge prerequisite, repeated clears and atomic reward persistence."""
import sys,tempfile,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.storage.challenge_state import ChallengeState,eligible
from els_server.storage.reward_state import RewardState

class ChallengeStateTests(unittest.TestCase):
 def test_phase_progress_prerequisites_retries_and_restart(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';clock=[100];s=ChallengeState(path,1001,clock=lambda:clock[0]);r=RewardState(path)
   attempt=s.begin(4,1);self.assertEqual(s.begin(4,1),attempt)
   self.assertIsNone(s.admit(34870));self.assertIsNone(s.admit(34880))
   for dungeon,progress in [(34850,1),(34860,3),(34870,7),(34870,15),(34880,31)]:
    effect={**s.admit(dungeon),'now':clock[0]};rid=str(uuid.uuid4())
    receipt=r.grant(rid,b'authenticated boss death',120,50,lambda b:b'encoded clear',challenge_clear=effect)
    self.assertFalse(receipt['replayed']);self.assertEqual(s.current()['progress'],progress)
    again=r.grant(rid,b'authenticated boss death',120,50,lambda b:self.fail('must replay saved C1'),challenge_clear=effect)
    self.assertTrue(again['replayed']);self.assertEqual(s.current()['progress'],progress)
    if dungeon==34850:self.assertIsNone(s.admit(dungeon))
   self.assertEqual(r.balances()['ed'],600);self.assertTrue(s.current()['complete'])
   self.assertEqual(ChallengeState(path,1001).current(),s.current())
   new=s.begin(4,1);self.assertNotEqual(new['attempt'],attempt['attempt']);self.assertEqual(new['progress'],0)
   self.assertIsNone(ChallengeState(path,1002,clock=lambda:100).current())

 def test_response_failure_rolls_back_rewards_and_progress(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';s=ChallengeState(path,1001,clock=lambda:100);s.begin(4,1);r=RewardState(path)
   effect={**s.admit(34850),'now':100};rid=str(uuid.uuid4())
   def fail(b):raise RuntimeError('injected C1 encoder failure')
   with self.assertRaises(RuntimeError):r.grant(rid,b'proof',120,50,fail,challenge_clear=effect)
   self.assertEqual(s.current()['progress'],0);self.assertEqual(r.balances()['ed'],0)
   self.assertFalse(r.grant(rid,b'proof',120,50,lambda b:b'clear',challenge_clear=effect)['replayed'])
   self.assertEqual(s.current()['progress'],1)

 def test_expiry_switch_and_stale_run_never_grant(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'save.sqlite3';clock=[100];s=ChallengeState(path,1001,clock=lambda:clock[0]);old=s.begin(5,1);r=RewardState(path)
   effect={**s.admit(34960),'now':100}
   with self.assertRaises(ValueError):s.begin(4,1)
   clock[0]=old['deadline'];self.assertIsNone(s.admit(34960))
   with self.assertRaises(ValueError):r.grant(str(uuid.uuid4()),b'proof',120,50,lambda b:b'clear',challenge_clear={**effect,'now':clock[0]})
   s.abandon();s.begin(5,1)
   with self.assertRaises(ValueError):r.grant(str(uuid.uuid4()),b'proof',120,50,lambda b:b'clear',challenge_clear=effect)
   self.assertEqual(r.balances()['ed'],0)

if __name__=='__main__':unittest.main()
