from pathlib import Path
import ast,hashlib,json
w=Path(__file__).resolve().parent;c=json.loads((w/'source-contract.json').read_bytes());assert len(c['files'])==2
for row in c['files']:
 p=w/'source/online'/row['path'];assert len(p.read_bytes())==row['size']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];ast.parse(p.read_bytes())
assert json.loads((w/'baseline-proof.json').read_bytes())['passed']
assert json.loads((w/'candidate-proof.json').read_bytes())['passed']
gui=json.loads((w/'sanitized-natural-GUI-proof.json').read_bytes());assert gui['passed']and gui['native_request_option']==1 and gui['box_removed']and gui['reward_count']==gui['open_receipts']==1
print('Archived source and original sender/session/user-assisted owned GUI evidence verified')
