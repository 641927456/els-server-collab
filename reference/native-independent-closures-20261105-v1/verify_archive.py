from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((H/'candidate-manifest.json').read_bytes())
assert len(m['files'])==26 and not m['full_guild_extensions_included'] and not m['pending_CP_support_included']
assert not m['new_hook'] and not m['installed'] and not m['natural_GUI']
for row in m['files']:
 p=(H/'source'/row['path']).resolve()
 assert p.is_relative_to(H/'source') and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 if p.suffix=='.py':ast.parse(p.read_bytes())
 elif p.suffix=='.json':json.loads(p.read_bytes())
v=json.loads((H/'verification.json').read_bytes())
assert v['ok'] and v['source_manifest_sha256']==sha(H/'candidate-manifest.json') and len(v['root_related_verification'])==4
assert not v['raw_runtime_traffic_included']
for p in H.glob('*.py'):ast.parse(p.read_bytes())
print('26 exact independent source/data identities and four sanitized related evidence families verified')
