import json,unittest
from els_server import diagnostic_reports as reports

class Classification(unittest.TestCase):
 def test_exact_failed_phase_observed_only(self):
  result=reports.classify({'attempt.json':json.dumps(dict(phase='component_update_failed')).encode()});self.assertEqual(result['code'],'launcher_component_update_failed');self.assertEqual(result['certainty'],'observed_stage');self.assertNotIn('confirmed',result['certainty'])
  for meta in ({'phase':'component_update'},{'phase':'unknown','component_error_type':'TimeoutException'},{'phase':'game_failed'},'component_update_failed'):
   result=reports.classify({'attempt.json':json.dumps(meta).encode(),'summary.json':b'{"launcher_metadata_only":true}'});self.assertEqual(result['code'],'insufficient_evidence',meta)
  self.assertEqual(reports.classify({'attempt.json':b'invalid json'})['code'],'insufficient_evidence')
 def test_existing_log_classification_preserved(self):
  for text,code in [('RelayBusyError','relay_busy'),('fingerprint mismatch','certificate_pin_mismatch'),('Account authentication failed','authentication_rejected')]:self.assertEqual(reports.classify({'logs/game-launch.log':text.encode()})['code'],code)

if __name__=='__main__':unittest.main(verbosity=2)
