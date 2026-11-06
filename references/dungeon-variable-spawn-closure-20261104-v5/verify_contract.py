"""Portable exact-source/data checks; private native/runtime evidence stays separate."""
import hashlib,json
from pathlib import Path
A=Path(__file__).resolve().parent;J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();c=J(A/'source-contract.json')
assert len(c['runtime_leaves'])==5 and len(c['development_tools'])==2 and not c['automatic_deployment']
for name,h in c['files'].items():
 p=A/'source'/name;assert H(p)==h,name
 if p.suffix=='.py':compile(p.read_bytes(),name,'exec')
for name,h in c['repair_sources'].items():assert H(A/'repair'/name)==h;compile((A/'repair'/name).read_bytes(),name,'exec')
for name,h in c['evidence'].items():assert H(A/name)==h,name
for stem in('els_server/data/client/dungeon_routes','els_server/data/formal_npc_hp'):
 assert H(A/'source'/(stem+'.json'))==J(A/'source'/(stem+'.manifest.json'))['payload_sha256']
assert H(A/'source/els_server/data/raid_npc_hp.json')==J(A/'source/els_server/data/formal_npc_hp.json')['sources']['raid_local_policy']
p=J(A/'source-chain-proof.json');g=J(A/'source/els_server/data/client/dungeon_routes.json');hp=J(A/'source/els_server/data/formal_npc_hp.json');raid=J(A/'source/els_server/data/raid_npc_hp.json')
key=lambda r:(r['dungeon'],r['stage'],r['target'])
expected={key(r)for r in p['chains']};assert len(expected)==len(p['chains'])==235 and len(p['qualified_maps'])==33
for r in p['chains']:
 assert r['edges'][0]['producer']==r['root']and r['edges'][-1]['target']==r['target']
 assert all(a['target']==b['producer']for a,b in zip(r['edges'],r['edges'][1:]))
 assert all(e['method'].lower()in('createnpcreq_lua','createnpchostreq_lua','init_special_riding_target')for e in r['edges'])
 assert r['target']in g['graphs'][r['source']]['stages'][str(r['stage'])]['allowed_summons']
 assert str(r['target'])in g['npcs']and str(r['target'])in hp['templates']
 if str(r['dungeon'])in raid['maps']:assert str(r['target'])in raid['maps'][str(r['dungeon'])]['templates']
for name in('dependency-domain-tests.json','dependency-TLS-tests.json'):
 result=J(A/name);assert result['ok']and len(result['cases'])==235 and{key(r)for r in result['cases']}==expected
sample=J(A/'current-parent-TLS-tests.json');assert sample['ok']and len(sample['cases'])==2 and{key(r)for r in sample['cases']}<=expected and sample['owned_database_removed']
generated=J(A/'final-cleanup-and-properties.json');assert generated['ok']and generated['property_program_oracles']==240 and generated['concrete_path_oracles']==480
assert generated['tested_flow_source_sha256']==H(A/'source/tools/npc_spawn_source_flow.py')
review=J(A/'missing-resource-review.json');assert review['ok']and len(review['rows'])==6 and review['executable_producers_for_these_absences']==0 and all(not r['original_Lua_restored']for r in review['rows'])
assert J(A/'native-flag-gate-tests.json')['ok']and J(A/'cleanup.json')['runtime_absent']
enum=J(A/'enum-reference-review.json');assert len(enum['inactive_current_stage_calls'])==2 and enum['unresolved_current_client_binding']['template']==12578 and not enum['unresolved_current_client_binding']['server_replacement_added']
print('Verified 7 exact source leaves, 235 matching domain/TLS cases, two current-parent TLS paths, independent-oracle binding and explicit client-source boundaries.')
