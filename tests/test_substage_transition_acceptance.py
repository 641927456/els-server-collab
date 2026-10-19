"""Do not accept a private B2 experiment, stale objects, or missing resume/movement."""
import copy,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from verify_substage_transition import evaluate
s=json.loads((BASE/'analysis/client-6c6b5180/20261013-181043/transition-phase-snapshot.json').read_text(encoding='utf8'))
identity,rows,server=s['identity'],s['rows'],s['server']
assert evaluate(identity,rows,server)['isolated_first_to_second_stage_verified']
for name in ['native_lifecycle_packet','updated_dungeon_frame','updated_input_finished']:
 assert not evaluate(identity,[r for r in rows if r.get('payload',{}).get('event')!=name],server)['isolated_first_to_second_stage_verified']
for kind in [0xad,0xbb,0xb3]:
 assert not evaluate(identity,rows,[r for r in server if not(r.get('event')=='decoded_client_event' and r.get('kind')==kind)])['isolated_first_to_second_stage_verified']
assert not evaluate(identity,rows,server+[{'event':'local_business_response_sent','kind':0xb2}])['isolated_first_to_second_stage_verified']
assert not evaluate(identity,rows+[{'type':'send','payload':{'event':'experimental_next_substage_dispatch'}}],server)['isolated_first_to_second_stage_verified']
assert not evaluate(identity,rows+[{'type':'error','description':'in-phase error'}],server)['isolated_first_to_second_stage_verified']
bad=copy.deepcopy(rows)
for r in bad:
 p=r.get('payload',{})
 if p.get('event')=='native_lifecycle_packet' and p.get('kind')==0xbd and (p.get('after') or {}).get('substage')==1:p['after']['suspended']=1
assert not evaluate(identity,bad,server)['isolated_first_to_second_stage_verified']
print('PASS: private dispatch, stale/missing population, missing wire/resume/movement, repeated stage delivery and in-phase errors reject transition acceptance.')
