from pathlib import Path
import ast,hashlib,json
root=Path(__file__).resolve().parent
contract=json.loads((root/'source-contract.json').read_bytes())
assert len(contract['files'])==1 and not contract['automatic_deployment']
for row in contract['files']:
    path=root/'source/online'/row['path']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    ast.parse(path.read_bytes())
assert contract['validation']['passed'] and contract['validation']['related_checks']==16
assert json.loads((root/'classification-retest.json').read_bytes())['passed']
assert len(json.loads((root/'scheduling-tests.json').read_bytes())['checks'])==4
application=json.loads((root/'application-tests.json').read_bytes())
assert application['passed'] and len(application['checks'])==6
assert json.loads((root/'application-cleanup.json').read_bytes())['runtime_removed']
print('One source SHA/syntax and recorded 16 related checks verified; no runtime or production test executed')
