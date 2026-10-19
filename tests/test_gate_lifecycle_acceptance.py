"""Require independent native, wire, locked-gate and identity witnesses."""
import copy,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE))
from verify_gate_lifecycle import evaluate
s=json.loads((BASE/'analysis/client-6c6b5180/20261013-174639/gate-lifecycle-phase-snapshot.json').read_text(encoding='utf8'))
identity,rows,server=s['identity'],s['rows'],s['server']
assert evaluate(identity,rows,server)['isolated_gate_lifecycle_verified']
for name in ['isolated_death_identity_repair','native_network_npc_death','native_lifecycle_packet','npc_live_diagnostics','updated_input_finished']:
 stripped=[r for r in rows if r.get('payload',{}).get('event')!=name]
 assert not evaluate(identity,stripped,server)['isolated_gate_lifecycle_verified'],name
for kind in [0xad,0xbb]:
 stripped=[x for x in server if not(x.get('event')=='decoded_client_event' and x.get('kind')==kind)]
 assert not evaluate(identity,rows,stripped)['isolated_gate_lifecycle_verified']
bad=copy.deepcopy(rows)
for r in bad:
 if r.get('payload',{}).get('event')=='isolated_death_identity_repair':r['payload']['original_lookup_matches']=False
assert not evaluate(identity,bad,server)['isolated_gate_lifecycle_verified']
assert not evaluate(identity,rows+[{'type':'error','description':'in-phase error'}],server)['isolated_gate_lifecycle_verified']
assert not evaluate(dict(identity,play=True),rows,server)['isolated_gate_lifecycle_verified']
print('PASS: missing native/wire/lock/repair witnesses, incorrect recipient match, in-phase error and nonisolated run all reject gate acceptance.')
