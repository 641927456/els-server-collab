from pathlib import Path
import ast,hashlib,json
root=Path(__file__).resolve().parent
m=json.loads((root/'candidate-manifest.json').read_bytes())
assert len(m['files'])==4 and m['new_tables']==[] and not m['client_changed']
for row in m['files']:
 p=root/'source'/row['path'];assert p.is_relative_to(root/'source')
 assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],row['path']
 ast.parse(p.read_bytes())
print('pet growth archive: 4 exact source hashes and syntax passed')
