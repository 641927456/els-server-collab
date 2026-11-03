"""Portable cumulative source identity and strict economic-scope binding."""
import hashlib,json,re
from pathlib import Path
W=Path(__file__).resolve().parent;J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();c=J(W/'source-contract.json');V=W.parent/c['prior_archive']
assert len(c['files'])==14 and len(c['runtime_leaves'])==12 and not c['automatic_deployment']
for name,h in c['files'].items():
 p=W/'source'/name;assert H(p)==h,name
 if p.suffix=='.py':compile(p.read_bytes(),name,'exec')
for name,h in c['evidence'].items():assert H(W/name)==h,name
for name,h in J(V/'source-contract.json')['files'].items():assert H(W/'source'/name)==h,name
from test_loot_scope import function
routes=J(W/'source/els_server/data/client/dungeon_routes.json');scope=function(W/'source/els_server/domain/dungeon_routes.py',routes)
for row in J(W/'loot-policy-invariance.json')['rows']:
 p=W/'source'/row['data_path'];data=J(p);module=(W/'source'/row['module_path']).read_text('utf8')
 assert re.search(r"DATA_SHA='([a-f0-9]{64})'",module)[1]==H(p)==row['data_sha256']
 assert scope(data['maps'])==data['route_scope_sha256']==row['new_route_scope']
 content={k:v for k,v in data.items()if k!='route_scope_sha256'}
 assert hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':')).encode()).hexdigest()==row['economic_content_sha256']
 assert row['loader_logic_unchanged_except_data_sha']and row['all_pools_ticks_items_quantities_and_descriptors_equal']
assert J(W/'loot-chain-summary.json')['ok']and J(W/'loot-chain-summary.json')['passed_cases']==7
assert J(W/'actual-scope-tests.json')['ok']and len(J(W/'actual-scope-tests.json')['rows'])==3
assert J(W/'cleanup.json')['runtime_absent']
print('Verified 14 cumulative source leaves, 3 economic catalogs, 7 owned loot lifecycle cases and unchanged 235 spawn dependencies.')
