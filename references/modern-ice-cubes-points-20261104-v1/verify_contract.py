from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent;c=json.loads((H/'source-contract.json').read_bytes());n=0
for channel in ('online','local'):
 rows=c[channel]['delta']if channel=='online'else c[channel]['files']
 assert len(rows)==13
 for r in rows:
  p=H/'source'/channel/r['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],p
  if p.suffix=='.py':ast.parse(p.read_bytes())
  else:json.loads(p.read_bytes())
  n+=1
assert json.loads((H/'session-proof.json').read_bytes())['all_passed']
assert json.loads((H/'session-proof-local.json').read_bytes())['all_passed']
print(str(n)+' source files, hashes, syntax and recorded Session validation verified; no runtime tests executed')
