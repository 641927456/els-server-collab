from pathlib import Path
import ast,hashlib,json
r=Path(__file__).resolve().parent
c=json.loads((r/'source-contract.json').read_bytes())
assert c['archive_only'] and len(c['files'])==17 and sum(x['parent_sha256'] is None for x in c['files'])==3
for x in c['files']:
 p=r/'source'/x['path'];assert len(p.read_bytes())==x['size'] and hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']
 if p.suffix=='.py':ast.parse(p.read_bytes())
assert hashlib.sha256((r/'source/launcher/Program.cs').read_bytes()).hexdigest()==c['launcher']['sha256']
assert json.loads((r/'evidence/test-summary.json').read_bytes())['ok']
assert json.loads((r/'evidence/protocol-verification.json').read_bytes())['passed']
assert json.loads((r/'evidence/traps.json').read_bytes())['ok']
assert json.loads((r/'evidence/quick-start.json').read_bytes())['passed']
profile=json.loads((r/'source/tools/client_compatibility_profiles.json').read_bytes())['profiles'][0]['artifacts']
for x in c['files']:
 if x['path'] in profile:assert profile[x['path']]==x['sha256']
assert len(profile)==65
print(json.dumps(dict(ok=True,runtime_delta=17,new_support=3,scope='archive identity/syntax and preserved execution evidence; no native/business rerun')))
