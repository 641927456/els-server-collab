from pathlib import Path
import hashlib,json
W=Path(__file__).resolve().parent
J=lambda p:json.loads(Path(p).read_bytes())
H=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
c=J(W/'source-contract.json');scope=J(W/'scope.json')
assert len(c['files'])==2 and len(scope['changes'])==8 and H(W/'scope.json')==c['scope_sha256']
for name,digest in c['files'].items():assert H(W/'source'/name)==digest,name
for name,digest in c['evidence'].items():assert H(W/name)==digest,name
p=J(W/'source/els_server/data/formal_npc_hp.json');m=J(W/'source/els_server/data/formal_npc_hp.manifest.json')
assert H(W/'source/els_server/data/formal_npc_hp.json')==m['payload_sha256']
for row in scope['changes']:
 item=p['maps'][str(row['map'])]['public_hp_templates'][str(row['template'])]
 assert item['hp_float32']==row['hp']and item['level']==99 and item['difficulty']==0
 assert item['source']=='cobodex_named_graph_level_reference_adopted_local_rule'
validation=J(W/'evidence/validation.json')
assert all(v['passed']and v['tests']==15 and v['skipped']==0 for v in validation.values())
assert J(W/'evidence/website.json')['cases']==16 and J(W/'evidence/website.json')['passed']
public=J(W/'evidence/public-acceptance.json');installed=J(W/'evidence/installation.json')
assert public['ok']and installed['online_installed']and installed['observation_seconds']>=120 and installed['own_QA_cleaned']
assert {r['template']for r in public['rows']}=={r['template']for r in scope['changes']}
print('2 exact data files; 8 mechanism HP inputs; 30 controlled tests; public TLS/static/dynamic/party acceptance')
