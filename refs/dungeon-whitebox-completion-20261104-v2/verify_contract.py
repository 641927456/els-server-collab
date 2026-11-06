from pathlib import Path
import ast,hashlib,json
W=Path(__file__).resolve().parent
J=lambda p:json.loads(p.read_bytes())
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
c=J(W/'source-contract.json');assert len(c['files'])==10 and H(W/'scope.json')==c['scope_sha256']
for name,digest in c['files'].items():
 p=W/name;assert H(p)==digest,name
 if p.suffix=='.py':ast.parse(p.read_text('utf8'))
for name,digest in c['evidence'].items():assert H(W/name)==digest,name
v=J(W/'evidence/validation.json');assert set(v)=={'online','local'}
assert all(r['distinct_related_checks']==7 and r['requester_refusal_cases']==23 and r['actual_TLS']and r['economic_state_unchanged']for r in v.values())
for ch in ('online','local'):
 data=J(W/'source'/ch/'els_server/data/native_line_triggers.json')
 keys=[(r['dungeon'],r['stage'],r['part'],r['trigger'])for r in data['rules']]
 assert len(keys)==len(set(keys))
print('10 pinned channel source files; completed-party correction; sanitized verification checked')
