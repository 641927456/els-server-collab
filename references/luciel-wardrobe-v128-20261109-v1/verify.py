from pathlib import Path
import ast,hashlib,json
r=Path(__file__).resolve().parent
c=json.loads((r/'source-contract.json').read_bytes());assert c['archive_only'] and not c['new_schema'] and len(c['files'])==2
for row in c['files']:
 p=r/'source'/row['path'];assert len(p.read_bytes())==row['size'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];ast.parse(p.read_bytes())
e=json.loads((r/'evidence/combined-TLS.json').read_bytes());assert e['ok'] and len(e['checks'])==22 and e['private_TLS_Application']
assert e['source_sha256']=={x['path']:x['sha256'] for x in c['files']}
assert json.loads((r/'evidence/accessory-pair.json').read_bytes())['ok']
print(json.dumps(dict(ok=True,files=2,scope='archive identity/syntax and preserved realTLS result; no fresh business run')))
