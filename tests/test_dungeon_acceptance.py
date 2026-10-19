"""Require native actor activity plus reviewed pixels; reject dispatch-only runs."""
import copy,json,sys,tempfile
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from verify_dungeon_entry import verify

source=Path(sys.argv[1])
trace=[json.loads(line) for line in (source/'launch-loopback-trace.jsonl').read_text(encoding='utf8').splitlines()]
capture=json.loads((source/'local-bootstrap.json').read_text(encoding='utf8'))
visual=json.loads((source/'dungeon-visual-review.json').read_text(encoding='utf8'))
with tempfile.TemporaryDirectory(prefix='dungeon-acceptance-',dir=BASE/'analysis') as folder:
    run=Path(folder)
    (run/'client-window-manual.png').write_bytes((source/'client-window-manual.png').read_bytes())
    for name in ['skill-a.png','skill-s.png']:
        if (source/name).exists():(run/name).write_bytes((source/name).read_bytes())
    (run/'local-bootstrap.json').write_text(json.dumps(capture),encoding='utf8')
    def check(rows,review=visual):
        (run/'launch-loopback-trace.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf8')
        (run/'dungeon-visual-review.json').write_text(json.dumps(review),encoding='utf8')
        return verify(run)
    result=check(trace)
    assert result['native_substage_start_observed'] and result['native_actor_updates_observed']
    assert result['native_actor_render_observed'] and result['character_visual_verified']
    for missing in ('begin','resume','render'):
        stripped=[]
        for row in trace:
            event=row.get('payload',{})
            excluded=(missing=='begin' and event.get('event')=='dungeon_native_dispatch' and event.get('message')==0xbd)
            excluded|=(missing=='resume' and event.get('event')=='dungeon_initialize_return' and event.get('function')=='0xf6c8b0')
            excluded|=(missing=='render' and event.get('event')=='native_player_lifecycle' and event.get('function')=='0x1e606d0')
            if not excluded:stripped.append(row)
        result=check(stripped)
        assert not result['native_substage_start_observed' if missing!='render' else 'character_visual_verified'],missing
    suspended=copy.deepcopy(trace)
    for row in suspended:
        event=row.get('payload',{})
        if event.get('event')=='native_dungeon_frame' and event.get('lifecycle'):
            event['lifecycle']['actors_suspended']=1
    assert not check(suspended)['native_substage_start_observed']
    assert not check(suspended)['character_visual_verified']
    assert not check(trace,{**visual,'actor_visible':False})['character_visual_verified']
    assert not check(trace+[{'type':'send','payload':{'event':'native_exception'}}])['character_visual_verified']
    assert not result['playable_scene_verified'] and not result['casting_verified']
print('PASS: real actor start/update/render and reviewed pixels; missing start/resume/render, suspended actors, invisible body and crash controls.')
