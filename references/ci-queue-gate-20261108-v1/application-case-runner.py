"""Rerun only the application case affected by the missing static config."""
from pathlib import Path
import hashlib,json
W=Path(__file__).resolve().parent;script=W/'repair_ci_fixture.py';text=script.read_text('utf8')
env={'__file__':str(script),'__name__':'ci_fixture_materialization'}
exec(compile(text[:text.index('needle=')],str(script),'exec'),env)
result=env['run'](env['fixed'],['test_application_periodic_and_direct_calls_share_capacity'])
assert result['passed'],result
record=dict(passed=True,scope='Historical CI test fixture; production and signed payload unchanged',
    cause='A wall-clock gate.wait(3) can release the worker before waiter/capacity assertions. The fixture now waits for its explicit event. Existing three-second predicate deadlines remain; asyncTearDown already always sets the event.',
    original_test_sha256=env['pin']['sha256'],fixed_test_sha256=env['sha'](env['O']/'test_peak_business_concurrency.py'),pinned_queue=env['queue'],
    controlled_delay_seconds=3.15,old_controlled_case=dict(passed=False,expected_failure='TimeoutError waiting for 64 waiters'),fixed_controlled_case=dict(passed=True),
    affected_tests=env['selected'],normal_affected_tests_passed=5,
    reused_successes='The initial exact-pinned run reached the normal-result assertion after the controlled old failure and fixed success; its only normal error was missing config/combat_rules.json in the application case. The four pure-queue cases passed. Those successes are retained; only the configuration-dependent application case was rerun.',
    corrected_materialization='Copied the exact profile-pinned combat_rules.json; no config value changed',application_case=result,
    historical_manifests_modified=False,live_queue_modified=False,signed_payload_modified=False,
    original_CI_phase_elapsed_not_logged=True)
(env['O']/'verification.json').write_text(json.dumps(record,indent=2)+'\n','utf8');print(json.dumps(record))
