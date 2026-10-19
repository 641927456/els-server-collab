"""Require actual native population/recipients and both network transitions."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_population import evaluate
s=json.loads((ROOT/'analysis/client-6c6b5180/20261013-185611/population-phase-snapshot.json').read_text(encoding='utf8'))
identity,rows,server=s['identity'],s['rows'],s['server']
def accepted(r=rows,w=server,i=identity):return evaluate(i,r,w)['isolated_original_population_and_boss_battle_verified']
assert accepted()
for name in ['updated_npc_factory_enter','updated_dungeon_frame','native_lifecycle_packet','native_network_npc_death','isolated_death_identity_repair']:
 assert not accepted([r for r in rows if r.get('payload',{}).get('event')!=name])
for kind in [0xad,0xbb,0xb3,0xb2]:
 assert not accepted(w=[e for e in server if e.get('kind')!=kind])
assert not accepted(rows+[{'type':'send','payload':{'event':'experimental_empty_clear_dispatch'}}])
assert not accepted(rows+[{'type':'error','description':'in-phase error'}])
assert not accepted(w=server+[{'event':'local_business_response_sent','kind':0xc1}])
bad=copy.deepcopy(rows)
for r in bad:
 e=r.get('payload',{})
 if e.get('event')=='updated_npc_factory_enter' and e.get('template')==5:e['template']=88
assert not accepted(bad)
bad=copy.deepcopy(rows)
for r in bad:
 e=r.get('payload',{})
 if e.get('event')=='isolated_death_identity_repair':e['original_lookup_matches']=False
assert not accepted(bad)
bad=copy.deepcopy(server)
for pos,e in enumerate(bad):
 if e.get('event')=='decoded_client_event' and e.get('kind')==0xad and (e.get('payload_hex') or '').startswith('00000000ff'):
  bad.insert(pos+1,{'event':'local_business_response_sent','kind':0xaf});break
assert not accepted(w=bad)
print('PASS: missing wire/native/identity evidence, wrong Boss template, private clear, unsupported death rewarded, in-phase errors reject acceptance.')
