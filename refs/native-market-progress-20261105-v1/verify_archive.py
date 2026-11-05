from pathlib import Path
import ast,hashlib,json
r=Path(__file__).resolve().parent
m=json.loads((r/'candidate-manifest.json').read_bytes())
assert len(m['files'])==2 and not m['new_tables'] and not m['client_changed']
for row in m['files']:
 p=r/'source'/row['path'];assert p.is_relative_to(r/'source')
 assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];ast.parse(p.read_bytes())
v=json.loads((r/'verification.json').read_bytes());assert v['ok'] and v['SQL_cases']==3
assert hashlib.sha256((r/'candidate-manifest.json').read_bytes()).hexdigest()==v['source_manifest_sha256']
for row in v['evidence']:
 p=r/row['path'];assert p.is_relative_to(r)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'] and json.loads(p.read_bytes())['ok']
print('Two exact source identities, syntax and three related SQL results passed')
