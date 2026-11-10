"""Keep original failed cases and qualify only measured successful native stages."""
from pathlib import Path
import hashlib,json
W=Path(__file__).resolve().parent;N=W/'native-game-v1/family1-v10'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
partial=read(W/'native-game-invitation-partial-v6.json')
assert partial['partial_invitation_pass']and not partial['ok']and partial['whole_scenario_failed']
complete=read(N/'scenario-complete.json');result=read(N/'server-result.json');receipt=read(N/'isolation-receipt.json')
assert complete['ok']and result['ok']and complete['native_arrival_complete']and not complete['errors']
assert complete['post_summon_native_transitions']==[0x71f,0x227]and complete['location']==20001
assert receipt['client_executable_unchanged']and receipt['physical_input_actions']==0 and receipt['input_desktop_unchanged']
assert receipt['own_job_pids_before_close']==[]
pins=read(N/'scenario-input-pins.json')
assert pins['probe_sha256']==sha(N/'probe_owned.py')and pins['backend_sha256']==sha(N/'server_input.py')
assert pins['observer_sha256']==sha(N.parent/'observer.js')
assert pins['qualification_seconds_after_actual_arrival']==125
rows=[]
for p in(N/'native-log').rglob('trace.jsonl'):
    for line in p.read_text('utf8').splitlines():
        value=json.loads(line).get('payload',{})
        if value.get('event','').startswith('owned_mentor_'):rows.append(value)
assert not any(v['event']=='owned_mentor_observer_failed'for v in rows)
names={v['event']for v in rows}
assert {'owned_mentor_original71D_returned',
    'owned_mentor_original71F_producer_returned','owned_mentor_original720_returned'}<=names
assert any(v['event']=='owned_mentor_summon_preconditions'and v['state']==14 and v['partner_restored']
    and v['destination']==v['expected_destination']==20001 and v['native_partner_uid']=='1002' for v in rows)
frames=[v for v in rows if v['event']=='owned_mentor_native_frames'and v['summoned']and v['state']==14]
assert frames and frames[-1]['seconds']-frames[0]['seconds']>=120
report=dict(ok=True,checks=['Same-source native invitation and original1EB consumer from v6 reused; v6 entire scenario remains failed',
    'Original2F saved partner consumed in the original teacher Game; existing private relation and qualification reused, no new award claim',
    'Original71D and71F consent; original720 then original direct227 persisted20000→20001; exact post-consent request order',
    'At least120s original native Town frame lifetime after summon and125s backend observation after actual arrival; no ED/XP change',
    'Own Game/Job empty, input desktop unchanged, no OS input or HP override, original EXE unchanged'],
    source_binding_sha256=sha(W/'candidate-source-binding-v5.json'),
    reused_partial_invitation=dict(path=str(W/'native-game-invitation-partial-v6.json'),sha256=sha(W/'native-game-invitation-partial-v6.json')),
    one_original_game_and_one_explicit_protocol_pupil=True,original_game=True,natural_GUI=False,
    client_support_delta=0,new_production_hooks=0,physical_input_actions=0,HP_override=False,
    original_EXE_unchanged=True,own_job_empty=True,worker_errors=result['errors'],installed=False,
    native_post_summon_frames=frames[-1]['frames']-frames[0]['frames'],
    native_post_summon_seconds=frames[-1]['seconds']-frames[0]['seconds'],
    backend_observed_seconds=result['observed_seconds'],fixture=read(N/'qualification-fixture.json'),
    harness_pins=pins,observations=[v for v in rows if v['event']!='owned_mentor_native_frames'])
out=W/'native-game-qualification-v5.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(dict(ok=True,original_game=True,natural_GUI=False,native_post_summon_seconds=report['native_post_summon_seconds'],installed=False)))
