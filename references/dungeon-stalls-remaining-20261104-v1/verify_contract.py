from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent
c=json.loads((H/'source-contract.json').read_bytes())
for n,h in c['files'].items():
 p=H/'source'/n
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,n
 if p.suffix=='.py':compile(p.read_bytes(),n,'exec')
for p in ('els_server/data/client/dungeon_routes','els_server/data/formal_npc_hp'):
 raw=(H/'source'/(p+'.json')).read_bytes();m=json.loads((H/'source'/(p+'.manifest.json')).read_bytes())
 assert hashlib.sha256(raw).hexdigest()==m['payload_sha256']
print('18 source leaves and both data payload contracts verified')
