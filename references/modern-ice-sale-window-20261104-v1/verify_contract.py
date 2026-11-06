from pathlib import Path
import ast,hashlib,json
W=Path(__file__).resolve().parent;c=json.loads((W/'source-contract.json').read_bytes())
assert len(c['files'])==4
for r in c['files']:
 p=W/'source/online'/r['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];ast.parse(p.read_bytes())
assert json.loads((W/'validation.json').read_bytes())['passed']
assert json.loads((W/'session-proof.json').read_bytes())['all_passed']
assert json.loads((W/'refresh-proof.json').read_bytes())['passed']
print('4 archived sources and recorded validation verified; runtime tests not executed')
