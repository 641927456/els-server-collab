"""Real native movement/skill effects, with independent acceptance controls."""
import copy,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from verify_dungeon_actions import evaluate_actions

run=Path(sys.argv[1])
events=[json.loads(line).get('payload',{}) for line in (run/'launch-loopback-trace.jsonl').read_text(encoding='utf8').splitlines()]
actors={e['main_actor'] for e in events if e.get('event')=='native_dungeon_frame' and e.get('main_actor') not in (None,'0x0')}
good=evaluate_actions(events,actors)
assert all(good[k] for k in good if k.endswith('_verified'))
assert not evaluate_actions([e for e in events if e.get('event')!='dungeon_action_state'],actors)['native_skill_a_effect_verified']
for name in ['stationary','no_jump','free_skill','no_release','wrong_actor','wrong_thread','nonfinite','failed_state']:
    bad=copy.deepcopy(events)
    for e in bad:
        action=e.get('action');kind=e.get('event')
        if name=='stationary' and action in ('left','right') and 'xyz' in e:e['xyz'][0]=0
        if name=='no_jump' and action=='jump' and 'xyz' in e:e['xyz'][1]=80
        if kind=='dungeon_input_sample':
            if name=='free_skill' and action=='skill_a':e['mp']=300
            if name=='no_release':e['release']=False
            if name=='wrong_actor':e['actor']='0x0'
            if name=='wrong_thread':e['thread']=-1
            if name=='nonfinite':e['xyz'][0]=float('nan')
        if name=='failed_state' and kind=='dungeon_action_state':e['result']=0
    result=evaluate_actions(bad,actors)
    key={'stationary':'native_movement_effect_verified','no_jump':'native_jump_effect_verified'}.get(name,'native_skill_a_effect_verified')
    assert not result[key],name
    if name in ('no_release','wrong_actor','wrong_thread','nonfinite'):assert result['completed_input_probes']==0,name
starts=[e['timestamp'] for e in events if e.get('event')=='dungeon_input_started' and e.get('action')=='skill_a']
repeat=starts[-1]
for name in ('insufficient_mp','extra_cost'):
    bad=copy.deepcopy(events);samples=[e for e in bad if e.get('event')=='dungeon_input_sample' and e.get('action')=='skill_a' and repeat<=e['timestamp']<=repeat+200]
    for i,e in enumerate(samples):e['mp']=90 if name=='insufficient_mp' else 200-(100 if i else 0)
    assert not evaluate_actions(bad,actors)['native_cooldown_rejection_verified'],name
print('PASS: real movement/jump/MP costs and cooldown; stationary, free cast, missing release, identity/thread, NaN, failed action, insufficient MP and duplicate-cost controls.')
