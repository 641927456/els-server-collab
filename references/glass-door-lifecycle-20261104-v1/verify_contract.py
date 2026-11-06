from pathlib import Path
import ast,hashlib,json
H=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_bytes())
c=read(H/'source-contract.json');q=c['qualification']
assert len(c['delta'])==4 and c['channels']==['online'] and not c['new_schema']
for row in c['delta']:
 p=H/'source/online'/row['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];ast.parse(p.read_bytes())
first=read(H/'verification.json');assert first['tests']==22 and len(first['failures'])==3 and all('GlassDoors.'not in f for f in first['failures'])
life=read(H/q['lifecycle']['file']);assert life['ok']and life['tests']==11 and life['skipped']==0
solo=read(H/q['TLS_solo']['file']);assert len(solo['checks'])==3 and solo['own_runtime_removed']
party=read(H/q['TLS_party']['file']);assert party['ok']and len(party['checks'])==2 and party['remaining_connections']==0
native=read(H/'native-timer-verification.json');assert native['ok']and len(native['scenarios'])==6
for name in('normal-protocol-precheck.json',c['normal_party_file']):
 r=read(H/name);assert r['ok']and r['own_runtime_removed']and not r['forced_server_room']
print('Four runtime source leaves and scoped recorded results verified; no private runtime tests executed')
