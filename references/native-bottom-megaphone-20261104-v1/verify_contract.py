"""Portable hash/syntax/evidence checks; does not claim a new runtime test."""
from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent;c=json.loads((H/'source-contract.json').read_bytes())
assert len(c['files'])==4 and not c['root_engine_changed']and not c['automatic_deployment']
for name,row in c['files'].items():
 p=H/row['source'];assert p.resolve().is_relative_to(H.resolve())and p.stat().st_size==row['size']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'],name
 if p.suffix=='.py':ast.parse(p.read_bytes())
 else:json.loads(p.read_bytes())
for name,pin in c['evidence'].items():assert hashlib.sha256((H/name).read_bytes()).hexdigest()==pin,name
for channel in('online','local'):
 j=json.loads((H/'validation'/('tests-'+channel+'.json')).read_bytes());assert j['passed']and j['tests_run']==9 and j['errors']==j['failures']==0
n=json.loads((H/'validation/native-proof-online.json').read_bytes());assert len(n['decoder_cases'])==3 and n['queued_count']==1 and n['panel']==5 and n['chat_category']==6
p=json.loads((H/'validation/public-acceptance.json').read_bytes());assert p['ok']and p['public_TLS']and len(p['checks'])==2 and p['runtime_periodic_path_verified']
d=json.loads((H/'validation/delivery-summary.json').read_bytes());assert d['ok']and d['online_installed']and not d['local_installed']and d['observation_seconds']>=120 and d['owned_QA_cleaned']
print(json.dumps(dict(ok=True,archived_source_files=4,recorded_tests_verified=True,runtime_tests_executed=False)))
