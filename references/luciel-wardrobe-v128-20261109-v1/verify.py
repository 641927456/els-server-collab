from pathlib import Path
import ast,hashlib,json
r=Path(__file__).resolve().parent
c=json.loads((r/'source-contract.json').read_bytes());assert c['archive_only'] and c['schema_change'] and len(c['files'])==9
for row in c['files']:
 p=r/'source'/row['path'];assert len(p.read_bytes())==row['size'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];ast.parse(p.read_bytes())
e=json.loads((r/'evidence/combined-TLS.json').read_bytes());assert e['ok'] and len(e['checks'])==22 and e['private_TLS_Application']
assert all(e['source_sha256'].get(x['path'],x['sha256'])==x['sha256'] for x in c['files'])
a=json.loads((r/'evidence/campaign.json').read_bytes());assert a['ok'] and a['tests']==10
b=json.loads((r/'evidence/runtime-bindings.json').read_bytes());assert {k.replace('.','/')+'.py':v['sha256'] for k,v in b.items()}=={x['path']:x['sha256'] for x in c['files']}
assert json.loads((r/'evidence/accessory-pair.json').read_bytes())['ok']
s=r/'supplements/shadow-castle-v127';h=json.loads((s/'handoff.json').read_bytes());assert not h['new_runtime_patch'] and len(h['runtime_binding'])==9
for item in h['source_tests']:assert hashlib.sha256((s/item['path']).read_bytes()).hexdigest()==item['sha256']
e=json.loads((s/'integrated-verification.json').read_bytes());assert len(e['routes'])==2 and all(v['ok'] and v['C1'] for v in e['routes'])
assert json.loads((r/'evidence/title-shortcuts.json').read_bytes())['ok']
assert json.loads((r/'evidence/title-boundaries.json').read_bytes())['ok']
assert json.loads((r/'evidence/title-native.json').read_bytes())['ok']
print(json.dumps(dict(ok=True,files=9,scope='archive identity/syntax and preserved realTLS result; no fresh business run')))
