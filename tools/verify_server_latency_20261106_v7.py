"""Verify the exact source-only latency overlay and its retained test evidence."""
from pathlib import Path
import ast,base64,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'refs/server-latency-20261106-v7'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 binding=read(D/'source-bindings.json');candidate=read(D/'candidate-v8.json');validation=read(D/'validation.json')
 assert binding['parent_git']=='64f2f5b1078c5d2db1992fbb156401c3c6c1cd0a'
 assert binding['source_files']==validation['source_bindings']
 assert set(candidate['files'])==set(binding['source_files'])and len(candidate['files'])==10
 for name,pin in candidate['files'].items():
  path=D/'source'/name;assert path.resolve().is_relative_to((D/'source').resolve())
  assert sha(path)==pin['after']==binding['source_files'][name]
  anchor=ROOT/binding['parent_git_files'][name];assert anchor.resolve().is_relative_to(ROOT.resolve())and sha(anchor)==pin['before']
  ast.parse(path.read_bytes(),filename=str(path))
 for group,folder in [('tests',D/'tests'),('receipts',D)]:
  for name,digest in validation[group].items():
   p=folder/name;assert p.resolve().parent==folder.resolve()and sha(p)==digest
   if p.suffix=='.py':ast.parse(p.read_bytes(),filename=str(p))
 for name in ['late-batch-baseline.json','late-batch-candidate.json','death-ready-writer-tests.json','coin-writer-tests.json','coin-writer-lifetime-tests.json','capped-death-clocks-tests.json','cloud-smoke.json']:
  assert read(D/name)['passed']
 assert binding['production_installed']is False and validation['production_installed']is False
 attendance=read(D/'attendance-preparation-tests.json');cloud=read(D/'cloud-c7-attendance-preflight.json')
 assert attendance['passed']and attendance['tests']==13 and not attendance['GIL_enabled']
 assert cloud['passed']and cloud['tests']==13 and not cloud['GIL_enabled']and not cloud['remaining_owned_pids']
 assert attendance['script_sha256']==sha(D/'tests/verify_attendance_preparation.py')==cloud['script_sha256']
 periodic=read(D/'cloud-c7-periodic-preflight.json')
 assert periodic['passed']and periodic['tests']==7 and not periodic['GIL_enabled']and not periodic['remaining_owned_pids']
 assert periodic['script_sha256']==sha(D/'tests/verify_periodic_followups.py')
 for receipt in [cloud,periodic]:
  assert all(binding['source_files'][k.removeprefix('candidate/')]==v for k,v in receipt['source_bindings'].items())
 negative=read(D/'periodic-followup-c5-armed-notification-failed.json')
 assert not negative['passed']and negative['tests']==7 and negative['failures']==1
 public=read(D/'cloud-native-c7-public20-v2.json')
 assert public['server_targets_met']and not public['public_relay_targets_met']and not public['overall_qualified']
 assert all(binding['source_files'][k]==v for k,v in public['source_bindings'].items())and not public['strict_five_Mbps_calibration_passed']
 assert public['durable_currency_exact']and public['acknowledged_currency_exact']and public['latency_samples_exact']and not public['connections']and public['owned_runtime_removed']
 before=read(D/'clock-race-before.json');fixed=read(D/'clock-race-fixed.json');frontend=read(D/'frontend-poll-deadline-tests.json')
 assert before['bug_reproduced']and not before['behavior_correct']and all(not c['native_clock_resumed']for c in before['cases'])
 assert fixed['passed']and fixed['behavior_correct']and len(fixed['cases'])==2 and all(c['native_clock_resumed']for c in fixed['cases'])
 assert frontend['passed']and frontend['tests']==4 and frontend['actual_same_account_frontend_and_game']
 for receipt in [fixed,frontend]:
  assert receipt['owned_runtime_removed']and not receipt['connections']and not receipt['errors']
  assert {k.removeprefix('candidate/'):v for k,v in receipt['source'].items()}==binding['source_files']
 public8=read(D/'cloud-native-c8-public-frontends20.json')
 assert public8['native_frontend_per_game']and public8['source_bindings']==binding['source_files']
 assert public8['overall_qualified']==validation['WAN_qualification_passed']
 assert public8['forward_counts']['matched']==public8['forward_counts']['drained']and public8['tcp_counter_samples']and not public8['tcp_counter_errors']
 assert read(D/'capped-party-gate-tests.json')['passed']and read(D/'local-native-c4-five.json')['cold_currency_and_ACK_exact']
 if (D/'launcher-build.json').exists():
  launcher=read(D/'launcher-build.json');checks=read(D/'launcher-v84-checks.json');endpoint=read(D/'endpoint-preview-v84-tests.json')
  assert launcher['parent_V']==83 and launcher['candidate_V']==84 and not launcher['published']
  assert launcher['candidate_launcher_sha256']==checks['exe_sha256']and checks['ok']and endpoint['passed']
  assert launcher['runtime_archive']['sha256']==checks['runtime_sha256']==endpoint['selected_payload_sha256']
  for name,row in launcher['source_changes'].items():assert sha(D/'launcher/source'/name)==row['after']['sha256']
  envelope=read(D/'launcher/source/resources/ui-scroll-signedFriends.signed.json')
  runtime=json.loads(base64.b64decode(envelope['payload']));members={r['path']:r for r in runtime['files']}
  assert len(members)==2786 and all(members[name]['sha256']==digest for name,digest in binding['source_files'].items())
 print(json.dumps(dict(ok=True,source_files=10,tests_bound=len(validation['tests']),receipts_bound=len(validation['receipts']),source_only=True,WAN_qualification_passed=validation['WAN_qualification_passed'])))
if __name__=='__main__':main()
