"""Verify archived source identities and existing result records; no runtime execution."""
from pathlib import Path
import ast,hashlib,json
r=Path(__file__).resolve().parent
c=json.loads((r/'source-contract.json').read_bytes())
assert len(c['files'])==3 and c['archive_only'] and not c['new_schema']
for row in c['files']:
 p=r/'source'/row['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];ast.parse(p.read_bytes())
for name in ('native-fixed.json','solo-settlement-passed.json','group-settlement-passed.json'):
 assert json.loads((r/'evidence'/name).read_bytes())['ok']
notice=(r/'source/els_server/protocol/raid_economy_protocol.py').read_text('utf8')
assert any(isinstance(n,ast.FunctionDef) and n.name=='weapon_snapshot' for n in ast.parse(notice).body)
print(json.dumps(dict(ok=True,files=3,scope='archive identity/syntax and preserved execution evidence; no fresh native/business run')))
