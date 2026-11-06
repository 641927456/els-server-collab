"""Check archived bytes and syntax without claiming a runtime test."""
from pathlib import Path
import ast,hashlib,json
root=Path(__file__).resolve().parent
contract=json.loads((root/'source-contract.json').read_bytes())
for name,expected in contract['files'].items():
    path=(root/name).resolve()
    assert path.is_relative_to(root.resolve())
    raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==expected,name
    if path.suffix=='.py':ast.parse(raw,filename=name)
    if path.suffix=='.json':json.loads(raw)
source=root/'source/online/els_server/domain/inventory_items.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==contract['candidate_leaf_sha256']
assert not contract['automatic_deployment']
print(json.dumps(dict(ok=True,archive_files=len(contract['files']),runtime_test_executed=False)))
