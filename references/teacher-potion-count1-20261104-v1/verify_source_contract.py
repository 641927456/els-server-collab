"""Verify exact dual-channel source and the already executed test bindings."""
from pathlib import Path
import hashlib,json

W=Path(__file__).resolve().parent
H=lambda b:hashlib.sha256(b).hexdigest()
J=lambda p:json.loads(p.read_bytes())
c=J(W/'source-contract.json')
assert {r['channel']for r in c['files']}=={'online','local'}
assert not c['automatic_deployment'] and not c['Git_merge']
for n,digest in c['evidence'].items():assert H((W/n).read_bytes())==digest,n
for r in c['files']:
    b=(W/r['channel']/r['path']).read_bytes()
    assert H(b)==r['candidate_sha256']
    new=b'if req.option not in (0,1) or any(';old=b'if req.option or any('
    assert b.count(new)==1 and H(b.replace(new,old))==r['parent_sha256']
    compile(b,r['channel']+'/'+r['path'],'exec')
    t=J(W/('tests-'+r['channel']+'.json'))
    assert t['ok'] and t['tests']==4 and not t['errors'] and not t['failures']
    assert t['binding']['candidate_sha256']==r['candidate_sha256']
    assert t['binding']['parent_sha256']==r['parent_sha256']
    assert t['temporary_databases_cleaned'] and not t['natural_GUI']
    assert {v['template']for v in t['rows']}=={721747,721748,721750,720487}
    assert all(all(v[k]for k in('preview','native_Count1','historical_Count0','exact_debit_and_rewards','invalid_counts_no_change','choice_rules','replay_no_increment','late_failure_rollback','cold_read'))for v in t['rows'])
print(json.dumps(dict(ok=True,source_files=2,one_line_delta_per_channel=True,existing_App_cases_bound=8,runtime_executed_by_this_check=False)))
