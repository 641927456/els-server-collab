"""Remove independent witnesses and require lifecycle acceptance to fail."""
import copy,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from verify_dungeon_lifecycle import evaluate
run=BASE/'analysis/client-6c6b5180/20261013-162654'
# Persistent run later performed resource diagnostics (including a rejected
# prefix guard). Freeze the originally observed lifecycle phase, not the
# mutable trace that unrelated later diagnostics keep appending to.
snapshot=json.loads((run/'lifecycle-phase-snapshot.json').read_text(encoding='utf8'))
identity=snapshot['identity'];rows=snapshot['rows'];server=snapshot['server']
assert evaluate(identity,rows,server)['fixture_lifecycle_verified']
for kind in [0xae,0xaf,0xba,0xbc]:
 stripped=[r for r in rows if not(r.get('payload',{}).get('event')=='native_lifecycle_packet' and r['payload'].get('kind')==kind)]
 assert not evaluate(identity,stripped,server)['fixture_lifecycle_verified']
for name in ['native_network_npc_death','updated_dungeon_frame']:
 assert not evaluate(identity,[r for r in rows if r.get('payload',{}).get('event')!=name],server)['fixture_lifecycle_verified']
for kind in [0xad,0xbb]:
 stripped=[e for e in server if not(e.get('event')=='decoded_client_event' and e.get('kind')==kind)]
 assert not evaluate(identity,rows,stripped)['fixture_lifecycle_verified']
assert not evaluate(identity,rows,server+[{'event':'local_business_response_sent','kind':0xbd}])['fixture_lifecycle_verified']
mutated=copy.deepcopy(rows)
for r in mutated:
 if r.get('payload',{}).get('event')=='native_network_npc_death':r['payload']['id']='100001'
assert not evaluate(identity,mutated,server)['fixture_lifecycle_verified']
bad=dict(identity,play=True);assert not evaluate(bad,rows,server)['fixture_lifecycle_verified']
assert not evaluate(identity,rows+[{'type':'error','description':'in-phase failure'}],server)['fixture_lifecycle_verified']
print('PASS: missing native/wire/frame evidence, wrong identity/NPC, repeated start all reject acceptance.')
