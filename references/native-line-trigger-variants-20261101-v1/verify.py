"""Check frozen source provenance without claiming to rerun TLS/native tests."""
from pathlib import Path
import ast,hashlib,json
O=Path(__file__).resolve().parent;R=O.parents[1]
J=lambda p:json.loads(p.read_bytes())
c=J(O/'source-contract.json');assert len(c['files'])==2 and c['issue']==707
for f in c['files']:
 p=R/f['source'];assert p.is_relative_to(O/'source/shared')and hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']
 if p.suffix=='.py':ast.parse(p.read_text('utf8'))
q=J(O/'qualified-activations.json');assert not q['failures']
rules=J(O/'source/shared/els_server/data/native_line_triggers.json')['rules']
key=lambda x:(x['dungeon'],x['stage'],x['part'],x.get('activation',x.get('trigger')))
qualified={key(x):x for x in q['qualified']}
assert len(rules)==len(qualified)==28 and len({r['dungeon']for r in rules})==11
for r in rules:
 a=qualified[key(r)]
 assert r['source_sha256']==a['source_sha256']and r['line_source_sha256']==a['line_source_sha256']
 assert r['world_source_sha256']==a['world']['sha256']and r['native_loop']==a['native_trigger']['TRIGGER_LOOP']
for channel in('online','local'):
 t=J(O/f'server-TLS-{channel}.json');assert t['ok']and t['actual_Application_TLS']and {key(x)for x in t['cases']}==set(qualified)
assert J(O/'native-activation-idempotency.json')['ok']
print(json.dumps(dict(ok=True,delivery_leaves=2,qualified_contexts=28,maps=11,recorded_TLS_channels=2,runtime_tests_reexecuted=False)))
