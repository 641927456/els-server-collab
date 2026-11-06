from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent;c=json.loads((H/'source-contract.json').read_bytes())
for r in c['delta']:
 p=H/'source'/r['channel']/r['leaf'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];ast.parse(p.read_bytes())
 first=json.loads((H/('tests-'+r['channel']+'-after.json')).read_bytes());follow=json.loads((H/('tests-'+r['channel']+'-followup.json')).read_bytes())
 assert first['tests']==5 and len(first['failures'])==1 and follow['ok'] and follow['tests']==1
for r in json.loads((H/'native-move-cold-read.json').read_bytes()):assert r['cold_read_after_shutdown'] and r['slots'][0]==0 and r['slots'][2]==25030 and r['revision']==1
print('Two one-file runtime deltas, syntax and recorded validation verified; no runtime tests executed')
