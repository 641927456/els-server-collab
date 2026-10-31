"""Verify the finite server-only phase and its complete actual-parent source map."""
from pathlib import Path
import ast,hashlib,json
from materialize_formal_runtime import plan
R=Path(__file__).resolve().parents[1];RID='current-obtainable-consumables-phase-20261028-v1'
read=lambda p:json.loads(p.read_bytes());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
d=read(R/'references'/RID/'delta.json');parent=read(R/d['parent']);candidate=read(R/'channels'/(RID+'.json'));q=read(R/'references'/RID/'qualification.json');schema=read(R/'references'/RID/'schema-allowlist.json')
assert q['ok']and q['client_changes']==q['new_client_files']==q['new_hooks']==q['test_window_operations']==q['install_DDL']==0
assert q['warehouse_scene_and_transfers_excluded']and not q['natural_GUI']and len(schema)==12
for ch in('online','local'):
 plan(R,parent,ch);plan(R,candidate,ch)
 before={r['path']:r for r in parent['channels'][ch]['files']};after={r['path']:r for r in candidate['channels'][ch]['files']};changes=d['channels'][ch]
 assert len(changes)==80 and len(set(after)-set(before))==38 and set(before)<=set(after)
 assert all(after[p]==v for p,v in before.items()if p not in changes)
 for rel,e in changes.items():
  assert rel.startswith('els_server/')and rel.endswith(('.py','.json'))and not any(s in rel for s in('guild_bank_capacity','guild_bank_items','guild_bank_rules','guild_bank_transfer'))
  assert(before.get(rel)or{}).get('sha256')==e['before_sha256']and after[rel]['sha256']==e['sha256']==sha(R/e['source'])
  if rel.endswith('.py'):ast.parse((R/e['source']).read_text('utf8'))
 coin=(R/changes['els_server/domain/guild_coin_flow.py']['source']).read_text('utf8');assert coin.count('result=0xb28')==3 and 'result=-1'not in coin and '0x526'not in coin
 assert all(after[p]==before[p]for p in('els_server/domain/ordinary_skill_pages.py','els_server/domain/owned_growth_items.py','els_server/domain/skill_state.py'))
 assert all(not p.startswith('tools/')for p in changes)
print(json.dumps(dict(ok=True,channels=2,delta=80,new_leaves=38,client_delta=0,new_hooks=0,install_DDL=0,warehouse_excluded=True)))
