"""Reuse completed business assertions; verify only the corrected log-kind gate."""
from pathlib import Path
import hashlib,json
F=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_bytes());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=max(F.glob('live-power-[0-9]*.json'));old=read(p)
assert old['ok']is False and old['owned_directory_removed']
assert 'line 112, in run'in old['error']and "all(row['event']=='protocol_error'"in old['error']
expected={('worker_error',"ValueError('Owned CP final encoding failure')"),
    ('protocol_error','Achievement native power inputs changed'),
    ('protocol_error','Raid native CP source/number')}
rows=old['observed_error_events'];assert len(rows)==3 and {(r['event'],r['error'])for r in rows}==expected
for name,digest in old['source_sha256'].items():assert sha(F/'source-v1'/name)==digest
before=(F/'test_live_power.attempt1.py').read_text('utf8')
assert before.splitlines()[111].strip()=="assert len(errors)==3 and all(row['event']=='protocol_error'for row in errors),errors"
assert 'report.update(ok=True'not in before[:before.index("assert len(errors)==3")]
result=dict(ok=True,scope='Read-only correction of the final diagnostic classification gate',
    original_scenario_ok=False,original_failure_retained=True,original_scenario=str(p),original_scenario_sha256=sha(p),
    original_script_sha256=sha(F/'test_live_power.attempt1.py'),corrected_script_sha256=sha(F/'test_live_power.py'),
    source_sha256=old['source_sha256'],business_source_changed=False,
    reused_business_assertions_before_failure_line=112,
    verified_before_failure=['Full native6BF payload','4199/4200/7000 thresholds',
        'Bare6BE and lowerCP do not mint/regress','Final encoding rollback',
        'Actual authoritative inventory changed between parse and writer rejected',
        'ForeignUID rejected','Large/repeated CP unchanged','Cold two-family same-account sharing',
        'Foreign account isolated'],
    corrected_log_gate_passed=True,expected_protocol_errors=2,expected_injected_worker_errors=1,
    unexpected_worker_notification_task_errors=0,whole_scenario_not_rerun=True,
    no_second_database_or_economy_replay=True,production_database_access=False,
    native_Game=False,natural_GUI=False,owned_directory_removed=True)
(F/'diagnostic-gate-qualification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(dict(ok=True,corrected_gate_only=True,reused_completed_business_assertions=True,original_whole_scenario_failure_retained=True)))
