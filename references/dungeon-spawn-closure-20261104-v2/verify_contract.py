from pathlib import Path
import hashlib,json
A=Path(__file__).resolve().parent;J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();c=J(A/'source-contract.json')
for name,h in c['files'].items():
 p=A/'source'/name;assert H(p)==h,name
 if p.suffix=='.py':compile(p.read_bytes(),name,'exec')
for name,h in c['repair_sources'].items():
 p=A/'repair'/name;assert H(p)==h;compile(p.read_bytes(),name,'exec')
for name in('els_server/data/client/dungeon_routes','els_server/data/formal_npc_hp'):
 assert H(A/'source'/(name+'.json'))==J(A/'source'/(name+'.manifest.json'))['payload_sha256']
assert H(A/'source/els_server/data/raid_npc_hp.json')==J(A/'source/els_server/data/formal_npc_hp.json')['sources']['raid_local_policy']
proof=J(A/'source-chain-proof.json');g=J(A/'source/els_server/data/client/dungeon_routes.json');hp=J(A/'source/els_server/data/formal_npc_hp.json');raid=J(A/'source/els_server/data/raid_npc_hp.json')
assert len(proof['chains'])==60 and len(proof['qualified_maps'])==20
for r in proof['chains']:
 assert r['edges'][0]['producer']==r['root']and r['edges'][-1]['target']==r['target']
 assert all(a['target']==b['producer']for a,b in zip(r['edges'],r['edges'][1:]))
 assert r['target']in g['graphs'][r['source']]['stages'][str(r['stage'])]['allowed_summons']
 assert str(r['target'])in g['npcs']and str(r['target'])in hp['templates']
 if str(r['dungeon'])in raid['maps']:assert str(r['target'])in raid['maps'][str(r['dungeon'])]['templates']
for name in('dependency-domain-tests.json','dependency-TLS-tests.json','parent-refusal-tests.json','cleanup.json'):assert J(A/name)['ok']
print('Six exact source leaves, payload/HP contracts and 60 stage dependency chains verified')
