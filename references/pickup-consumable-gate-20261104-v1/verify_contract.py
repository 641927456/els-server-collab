from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent;c=json.loads((H/'source-contract.json').read_bytes())
for name,digest in c['files'].items():
 p=H/'source'/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==digest,name;ast.parse(p.read_bytes())
for name in ('variant-tests.json','tls-tests.json','initial-pickup-tests.json','initial-gate-tests.json','initial-gate-tls-tests.json','initial-consumable-tests-candidate.json'):
 assert json.loads((H/name).read_bytes())['ok'],name
guard=json.loads((H/'guard-results.json').read_bytes());assert guard['before']['count']==15 and guard['after']['count']==0
print('14 runtime leaves, related validation and regression guard verified')
