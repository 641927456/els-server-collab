"""Real complete native sweep, plus controls for missing checks and dialogs."""
import copy,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from verify_experiment import evaluate
from resource_integrity import LOCAL_DIGEST
folder=Path(sys.argv[1]) if len(sys.argv)>1 else BASE/'analysis/runs/20261012-171840-965354'
trace=[json.loads(l) for l in (folder/'launch-loopback-trace.jsonl').read_text(encoding='utf8').splitlines()]
probe=json.loads((folder/'launch-loopback.json').read_text())
capture=json.loads((folder/'local-bootstrap.json').read_text())
result=evaluate(trace,probe,capture)
assert result['resource_integrity_sweep_verified'] and result['resource_integrity_checked_files']==36
assert result['character_list_verified'] and result['channel_list_verified']
audit={r['file']:r for r in json.loads((BASE/'analysis/archive-integrity-audit.json').read_text(encoding='utf-8-sig'))}
pending={};verified=set()
for r in trace:
    e=r.get('payload',{});kind=e.get('event');thread=e.get('thread')
    if kind=='archive_integrity_input':pending[thread]={'file':e['file']}
    elif kind=='archive_integrity_actual' and thread in pending:pending[thread]['digest']=e['hex']
    elif kind=='archive_integrity_result' and thread in pending:
        p=pending.pop(thread)
        assert e['file']==p['file'] and e['result']==1
        assert p['digest']==audit[p['file']]['local_digest']
        verified.add(p['file'])
assert verified==set(audit)
missing=[r for r in trace if not (r.get('payload',{}).get('event')=='archive_integrity_result' and r['payload'].get('file')=='data002.kom')]
assert not evaluate(missing,probe,capture)['resource_integrity_sweep_verified']
wrong=copy.deepcopy(trace)
for r in wrong:
    e=r.get('payload',{})
    if e.get('event')=='archive_integrity_actual' and e.get('hex')==LOCAL_DIGEST:e['hex']='0'*40
assert not evaluate(wrong,probe,capture)['resource_integrity_verified']
dialog={'type':'send','payload':{'event':'native_dialog','text':'datai030.kom is Invalid','timestamp':next(r['payload']['timestamp'] for r in trace if r.get('payload',{}).get('event')=='archive_integrity_input')}}
assert not evaluate(trace+[dialog],probe,capture)['startup_verified']
assert not evaluate(trace+[dialog],probe,capture)['resource_integrity_sweep_verified']
for missing_event in ['channel_record_parsed','channel_list_handler_return']:
    shortened=[r for r in trace if r.get('payload',{}).get('event')!=missing_event]
    assert not evaluate(shortened,probe,capture)['channel_list_verified']
print('PASS: all 36 independent/native digests agree; complete sweep and channel gates reject missing or wrong evidence and dialogs.')
