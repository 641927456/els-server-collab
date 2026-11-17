"""Verify exact review identities and keep incomplete qualification explicit."""
from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((H/'candidate-manifest.json').read_bytes())
assert len(m['files'])==109 and not m['install_ready'] and not m['natural_GUI']
assert len(m['pending_support'])==4 and len(m['policies_awaiting_user'])==3
for row in m['files']:
 p=(H/'source'/row['path']).resolve()
 assert p.is_relative_to(H/'source') and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 if p.suffix=='.py':ast.parse(p.read_bytes())
 elif p.suffix=='.json':json.loads(p.read_bytes())
v=json.loads((H/'verification.json').read_bytes())
assert v['ok'] and v['source_manifest_sha256']==sha(H/'candidate-manifest.json')
assert len(v['inherited_successful_families'])==34 and len(v['root_related_tests'])==9
assert not v['raw_runtime_traffic_included'] and not v['install_ready'] and not v['natural_GUI']
for name in('initial_smashes','held_badge_and_contract'):
 p=H/'source/els_server/data'/('guild_expedition_policy.json'if name=='initial_smashes'else'guild_profession_policy.json')
 assert json.loads(p.read_bytes())[name]is None
assert json.loads((H/'source/els_server/data/guild_seed_pouch_policy.json').read_bytes())['templates']is None
for p in H.glob('*.py'):ast.parse(p.read_bytes())
print('109 exact reviewed files, 34 inherited and 9 related evidence families; pending qualification remains explicit')
