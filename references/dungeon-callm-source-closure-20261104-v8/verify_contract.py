import hashlib,json
from pathlib import Path
W=Path(__file__).resolve().parent;J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();c=J(W/'source-contract.json')
assert len(c['files'])==7 and len(c['runtime_leaves'])==5 and not c['automatic_deployment']
for name,h in c['files'].items():
 p=W/'source'/name;assert H(p)==h,name
 if p.suffix=='.py':compile(p.read_bytes(),name,'exec')
for name,h in c['evidence'].items():assert H(W/name)==h,name
for stem in('els_server/data/client/dungeon_routes','els_server/data/formal_npc_hp'):assert H(W/'source'/(stem+'.json'))==J(W/'source'/(stem+'.manifest.json'))['payload_sha256']
assert H(W/'source/els_server/data/raid_npc_hp.json')==J(W/'source/els_server/data/formal_npc_hp.json')['sources']['raid_local_policy']
p=J(W/'source-chain-proof.json');routes=J(W/'source/els_server/data/client/dungeon_routes.json');key=lambda r:(r['dungeon'],r['stage'],r['target']);expected={key(r)for r in p['paths']};assert len(expected)==9 and len({x[0]for x in expected})==3
for r in p['paths']:assert r['target']in routes['graphs'][r['source']]['stages'][str(r['stage'])]['allowed_summons']
for name in('dependency-domain-tests.json','dependency-TLS-tests.json','parent-refusals.json'):
 r=J(W/name);assert r['ok']and{key(v)for v in r['cases']}==expected
assert J(W/'user-creator-and-loot-tests.json')['economic_catalog_maps']==[53,33,22]
native=J(W/'native-event-priority-tests.json');assert native['ok']and len(native['rate_dispatch'])==4 and len(native['successful_change_stops_before_next_event'])==16 and native['unchanged_counter_negative_cases']==16
closed=J(W/'henir-source-boundary-closure.json');assert closed['ok']and len(closed['contexts'])==2 and all(x['required_original_sources_complete']and not x['missing_enum_callback_reachable']and not x['missing_script_12582_has_executable_producer']for x in closed['contexts'])
assert J(W/'cleanup.json')['runtime_absent']
print('Verified 9 matching source/domain/TLS/parent cases, original 12585 identity, native event priority and complete active Henir sources.')
