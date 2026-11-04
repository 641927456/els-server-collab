from pathlib import Path
import ast,hashlib,json
root=Path(__file__).resolve().parent
contract=json.loads((root/'source-contract.json').read_bytes())
assert len(contract['files'])==3 and not contract['installed'] and not contract['automatic_deployment']
for row in contract['files']:
    path=root/'source/online'/row['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],row['path']
    ast.parse(path.read_bytes())
targeted=json.loads((root/'atomic-reply-proof.json').read_bytes())
existing=json.loads((root/'existing-regression-proof.json').read_bytes())
assert targeted['passed'] and len(targeted['checks'])==5
assert existing['passed'] and existing['cases']==9 and not existing['skipped']
print('3 source hashes/syntax and recorded 5+9 checks verified; no runtime or production test executed')
