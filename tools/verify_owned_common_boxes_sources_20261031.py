"""Verify the exact qualified LOCAL/online leaves without activating old root code."""
from pathlib import Path
import ast,hashlib,json
R=Path(__file__).resolve().parents[1];A=R/'references/owned-common-boxes-dual-20261031-v1'
contract=json.loads((A/'source-contract.json').read_bytes());seen=set()
for channel,row in contract['channels'].items():
 assert len(row['files'])==27 and row['client_delta']==0
 for item in row['files']:
  p=R/item['source'];assert p.resolve().is_relative_to((R/'references').resolve())
  raw=p.read_bytes();assert len(raw)==item['size']and hashlib.sha256(raw).hexdigest()==item['sha256'],item['path']
  ast.parse(raw)if p.suffix=='.py'else json.loads(raw);seen.add(item['source'])
assert len(seen)==31
assert contract['validation']['local_templates']==76 and contract['validation']['online_local_session_passed']==75
assert contract['validation']['online_friends_actor_cases']==4 and contract['validation']['public_TLS_templates']==12
assert contract['installed']['online']and contract['installed']['local']and not contract['installed']['Git_merge']
public=json.loads((A/'public-acceptance.json').read_bytes())
assert public['ok']and public['cold_authenticated_restore']and len(public['checks'])==12
assert {r['template']for r in public['checks']}=={723612,723618,723673,723680,721780,119335,303673,30615,117542,109999,135666,300645}
assert all(r['Count1']and r['bulk2_rejected']for r in public['checks'])
for row in contract['evidence']:
 raw=(R/row['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==row['sha256']
print(json.dumps(dict(ok=True,channels=2,changed_each=27,unique_sources=len(seen),public_TLS_templates=12,root_runtime_switched=False)))
