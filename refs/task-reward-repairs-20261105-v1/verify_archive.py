"""Check the exact archived payload; this does not rerun private gameplay tests."""
from pathlib import Path
import ast,hashlib,json
ROOT=Path(__file__).resolve().parent
contract=json.loads((ROOT/'source-contract.json').read_bytes())
assert contract['reference_only']and not contract['installed']and len(contract['source_files'])==26
paths=set()
for row in contract['source_files']:
 path=(ROOT/row['archive_path']).resolve()
 assert path.is_relative_to(ROOT)and path not in paths
 paths.add(path);raw=path.read_bytes()
 assert len(raw)==row['bytes']and hashlib.sha256(raw).hexdigest()==row['sha256'],str(path)
 if path.suffix=='.py':ast.parse(raw.decode('utf8'),filename=str(path))
 else:json.loads(raw)
for row in contract['verification_scripts']:
 path=ROOT/row['path'];raw=path.read_bytes()
 assert hashlib.sha256(raw).hexdigest()==row['sha256'],str(path)
 ast.parse(raw.decode('utf8'),filename=str(path))
reports=json.loads((ROOT/contract['validation']).read_bytes())
assert all(row['ok']for row in reports.values())
print(json.dumps(dict(ok=True,source_files=len(paths),verification_scripts=len(contract['verification_scripts']),business_tests_not_rerun=True)))
