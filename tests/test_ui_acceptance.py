"""Native HUD evidence is required; partial parsing and missing ACKs fail."""
import json,copy,sys,tempfile
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from verify_ui_layout import verify
run=BASE/'analysis/runs/20261012-194401-991319'
trace=[json.loads(l) for l in (run/'launch-loopback-trace.jsonl').read_text(encoding='utf8').splitlines()]
capture=(run/'local-bootstrap.json').read_text(encoding='utf8')
with tempfile.TemporaryDirectory(prefix='hud-proof-',dir=BASE/'analysis') as folder:
    target=Path(folder);(target/'local-bootstrap.json').write_text(capture,encoding='utf8')
    def check(rows):
        (target/'launch-loopback-trace.jsonl').write_text('\n'.join(json.dumps(e) for e in rows),encoding='utf8')
        return verify(target)
    good=check(trace);assert good['ui_layout_verified'] and good['ui_layout_save_verified']
    broken=copy.deepcopy(trace)
    for e in broken:
        if e.get('payload',{}).get('event')=='ui_layout_consumed':e['payload']['fields'][-1]['ok']=0
    assert not check(broken)['ui_layout_verified']
    broken=[e for e in trace if e.get('payload',{}).get('event')!='ui_layout_save_ack_consumed']
    assert not check(broken)['ui_layout_save_verified']
    broken=[e for e in trace if not (e.get('payload',{}).get('event')=='request_wait_removed' and e['payload'].get('message')==0x6ec)]
    assert not check(broken)['ui_layout_save_verified']
    assert not check(trace+[{'type':'error','description':'Injected negative witness'}])['ui_layout_verified']
print('PASS: native HUD parsing and save ACK witnesses; missing/failed fields, waits and probe errors rejected.')
