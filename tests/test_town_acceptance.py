"""Use real native city evidence; reject crashes, wrong locations and UI-only state."""
import copy,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from verify_experiment import evaluate
run=BASE/'analysis/runs/20261012-182959-314742'
trace=[json.loads(l) for l in (run/'launch-loopback-trace.jsonl').read_text(encoding='utf8').splitlines()]
probe=json.loads((run/'launch-loopback.json').read_text(encoding='utf8'))
capture=json.loads((run/'local-bootstrap.json').read_text(encoding='utf8'))
assert evaluate(trace,probe,capture)['town_entry_verified']
for name in ['field_frame','field_scene_lookup_return','player_initialization_parsed','square_entry_payload_parsed']:
    stripped=[e for e in trace if e.get('payload',{}).get('event')!=name]
    assert not evaluate(stripped,probe,capture)['town_entry_verified'],name
wrong=copy.deepcopy(trace)
for e in wrong:
    if e.get('payload',{}).get('event')=='field_frame':e['payload']['stage_map']=30000
assert not evaluate(wrong,probe,capture)['town_entry_verified']
crashed=copy.deepcopy(probe);crashed['exited_before_cleanup']=True;crashed['exit_code_before_cleanup']=0xffffffff
assert not evaluate(trace,crashed,capture)['town_entry_verified']
bad=copy.deepcopy(capture)
for c in bad['connections']:
    for e in c.get('decoded_events',[]):
        if e['kind']==0x225:e['mac_verified']=False
assert not evaluate(trace,probe,bad)['town_entry_verified']
print('PASS: real town entry; native scene/player evidence, map, crash and authenticated request controls.')
saved_run=BASE/'analysis/runs/20261012-194401-991319'
saved_trace=[json.loads(l) for l in (saved_run/'launch-loopback-trace.jsonl').read_text(encoding='utf8').splitlines()]
saved_probe=json.loads((saved_run/'launch-loopback.json').read_text(encoding='utf8'))
saved_capture=json.loads((saved_run/'local-bootstrap.json').read_text(encoding='utf8'))
assert evaluate(saved_trace,saved_probe,saved_capture)['town_entry_verified']
wrong_scene=copy.deepcopy(saved_trace)
for e in wrong_scene:
    if e.get('payload',{}).get('event')=='field_scene_lookup_return':e['payload']['requested']=258
assert not evaluate(wrong_scene,saved_probe,saved_capture)['town_entry_verified']
print('PASS: real saved Elder entry (20001/263), mismatching original town scene rejected.')
