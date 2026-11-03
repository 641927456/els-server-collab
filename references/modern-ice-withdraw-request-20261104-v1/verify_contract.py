from pathlib import Path
import ast,hashlib,json
W=Path(__file__).resolve().parent;c=json.loads((W/'source-contract.json').read_bytes());assert len(c['files'])==1
for r in c['files']:
 p=W/'source/online'/r['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];ast.parse(p.read_bytes())
native=json.loads((W/'native-request-proof.json').read_bytes());assert native['passed'] and all(r['kind']==0xbd3 for r in native['cases'])
assert json.loads((W/'withdraw-proof.json').read_bytes())['passed']
assert json.loads((W/'variant-review.json').read_bytes())['passed']
print('Archived withdrawal source and original-sender/session evidence verified; runtime tests not rerun')
