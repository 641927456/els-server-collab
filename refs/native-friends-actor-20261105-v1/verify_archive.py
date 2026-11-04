from pathlib import Path
import ast,hashlib,json
root=Path(__file__).resolve().parent
m=json.loads((root/'candidate-manifest.json').read_bytes())
assert len(m['files'])==7 and not m['client_changed']
for row in m['files']:
 p=root/'source'/row['path'];assert p.is_relative_to(root/'source')
 assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row['path']
 ast.parse(p.read_bytes())
v=json.loads((root/'verification.json').read_bytes());assert v['ok']
for row in v['evidence']:
 p=root/row['path'];assert p.is_relative_to(root)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'] and json.loads(p.read_bytes())['ok']
print('Seven source identities, syntax and related success evidence passed')
