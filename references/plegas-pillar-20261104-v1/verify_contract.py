"""Verify archived source and recorded acceptance, without claiming a live rerun."""
from pathlib import Path
import ast,base64,hashlib,json
H=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
c=read(H/'source-contract.json');assert len(c['files'])==7 and not c['server_changes'] and not c['LOCAL_changes'] and not c['automatic_deployment']
for name,row in c['files'].items():
 p=H/row['path'];assert p.resolve().is_relative_to(H.resolve()) and p.stat().st_size==row['size'] and sha(p)==row['sha256'],name
 if p.suffix=='.py':ast.parse(p.read_bytes())
 elif p.suffix=='.json':read(p)
for name,pin in c['evidence'].items():assert sha(H/name)==pin,name
assert sha(H/'launcher-source-inventory.json')==c['launcher_source_inventory_sha256']
v=H/'validation';n=read(v/'native-live-candidate.json');assert n['ok'] and n['native_counts']==list(range(1,51))
assert read(v/'adapter-tests.json')['tests']==19 and len(read(v/'native-hp-floor-proof.json')['cases'])==6
r=read(v/'actual-ready.json');assert r['ok'] and r['native_ready_events']==1
p=read(v/'public-upgrade.json');assert p['ok'] and p['public_TLS_signed_component_selection'] and p['all_components_verified']==1806 and p['changed_downloads']==4 and p['repeat_downloads']==0
i=read(v/'installation.json');assert i['ok'] and i['observation_seconds']>=120 and i['V']==75 and i['player_database_changes']==0
env=read(H/'source/launcher/resources/ui-scroll-signedFriends.signed.json');rows=json.loads(base64.b64decode(env['payload']))['files'];byname={r['path']:r for r in rows};assert len(rows)==1806
for name,row in c['files'].items():
 if name.startswith('client/'):assert byname[name[7:]]['sha256']==row['sha256']
print(json.dumps(dict(ok=True,source_files=7,recorded_acceptance_verified=True,runtime_rerun=False)))
