from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_bytes())
c=read(H/'source-contract.json');s=read(H/'scope.json')
for name,digest in c['files'].items():
 p=H/'source'/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==digest,name
 if p.suffix=='.py':ast.parse(p.read_text('utf8'))
for name,digest in c['evidence'].items():assert hashlib.sha256((H/name).read_bytes()).hexdigest()==digest
data=read(H/'source/els_server/data/consumable_extensions.json')
module=(H/'source/els_server/domain/consumable_extensions.py').read_text('utf8')
assert hashlib.sha256((H/'source/els_server/data/consumable_extensions.json').read_bytes()).hexdigest()in module
assert len(s['added'])==len(set(s['added']))==116
assert {r['template']for r in s['excluded']}=={78430,711606} and not set(s['added'])&{78430,711606}
definitions={r['template']:r for r in data['quick']}
for row in s['scope']:
 if row['template']in s['added']:
  assert {k:v for k,v in row.items()if k not in ('already_admitted','npc_recipes')}==definitions[row['template']]
t=read(H/'evidence/transaction-tests-run3.json');p=read(H/'evidence/tls-candidate-run3.json');craft=read(H/'evidence/crafting-tests.json')
assert t['ok']and t['tests']==3 and t['skipped']==0 and len(t['templates'])==138
assert p['ok']and not p['errors']and p['connections']==0 and len(p['templates'])==138
assert craft['ok']and len(craft['rows'])==70 and all(r['crafted_used_and_cold_read']for r in craft['rows'])
native=[read(H/'evidence'/n)for n in ('native-inputs.json','native-npc-inputs.json')]
assert all(n['ok']for n in native)and sum(len(r['cases'])for n in native for r in n['rows'])==414
assert t['candidate_files']==p['candidate_files']==craft['candidate_files']==c['files']
print('Two exact runtime files;116 added;138 tested;70 crafted/used;414 native inputs;2 excluded')
