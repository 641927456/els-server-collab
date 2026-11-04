from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent;m=json.loads((H/'source-manifest.json').read_bytes())
for row in m['files']:
 p=H/row['path'];assert p.stat().st_size==row['size']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row['path']
 if p.suffix=='.py':ast.parse(p.read_text('utf8'))
for row in m['changes']:
 assert hashlib.sha256((H/'source'/row['path']).read_bytes()).hexdigest()==row['sha256']
 if row['parent_sha256']is not None:assert hashlib.sha256((H/'base'/row['path']).read_bytes()).hexdigest()==row['parent_sha256']
 else:assert not(H/'base'/row['path']).exists()
q=json.loads((H/'qualification.json').read_bytes());assert q['passed']and(q['misc_cases'],q['completion_cases'],q['previous_material_cases'])==(24,19,18)
assert json.loads((H/'recovery-reader-verification.json').read_bytes())['passed']
print(json.dumps(dict(ok=True,runtime_delta=len(m['changes']),archive_files=len(m['files']),new_client_files=0,player_database_restore=False)))
