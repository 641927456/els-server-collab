"""Verify source attribution integration without enabling attribute delivery."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import plan
read=lambda p:json.loads(p.read_bytes())
sha=lambda b:hashlib.sha256(b).hexdigest()
F=ROOT/'references/native-skill-source-runtime-20261028-v1'
d=read(F/'delta.json');b=read(F/'binding.json');m=read(F/'manifest.json')
p=read(ROOT/d['parent']);c=read(ROOT/'channels/native-skill-source-runtime-20261028-v1.json')
assert m['existing_runtime_leaves']==13 and m['new_runtime_modules']==6 and m['total_runtime_leaves']==19
assert m['attribute_delivery_admission']is False
assert all(m[k]==0 for k in ('new_tables','install_DDL','client_files','new_hooks','additional_packets','additional_SQL'))
for channel in ('online','local'):
 old={r['path']:r for r in p['channels'][channel]['files']};rows={r['path']:r for r in c['channels'][channel]['files']}
 changed=d['channels'][channel];new=set(b['new_modules'])
 assert len(changed)==19 and len(rows)==len(old)+6 and rows.keys()-old.keys()==new
 assert {n for n in rows if rows[n]!=old.get(n)}==set(changed)
 for key in ('retained_client_sources','retained_client_support_sources','retained_signed_launcher_sha256','retained_signed_payload_sha256'):
  assert p['channels'][channel].get(key)==c['channels'][channel].get(key)
 bindings={r['path']:r for r in b['existing']if r['channel']==channel}
 assert set(bindings)==set(changed)-new
 for path,entry in changed.items():
  raw=(ROOT/entry['source']).read_bytes();ast.parse(raw)
  assert sha(raw)==rows[path]['sha256']==entry['sha256']and len(raw)==rows[path]['size']
  if path in new:
   assert entry['before_sha256']is None
   assert not any(word in raw for word in (b'Interceptor.',b'Memory.write',b'ALTER TABLE',b'CREATE TABLE'))
   continue
  binding=bindings[path];before=(ROOT/binding['parent_source']).read_bytes()
  assert sha(before)==binding['parent_sha256']==entry['before_sha256']==old[path]['sha256']
  inverse=raw.decode('utf8')
  for edit in reversed(binding['changes']):
   assert not any(word in edit['after']for word in ('Interceptor.','Memory.write','ALTER TABLE','CREATE TABLE'))
   assert inverse.count(edit['after'])==1
   inverse=inverse.replace(edit['after'],edit['before'],1)
  assert inverse.encode()==before
 plan(ROOT,c,channel)
session=(F/'common/els_server/domain/native_session_sources.py').read_text('utf8')
assert 'actor_ready=False'in session and 'prepare('not in session and '0x106'not in session
dep=b['unchanged_relative_dependency'];raw=(F/dep['path']).read_bytes()
assert sha(raw)==dep['sha256']and dep['runtime_delta']is False
for ch in ('online','local'):
 assert next(r for r in p['channels'][ch]['files']if r['path']==dep['runtime_path'])['sha256']==sha(raw)
if (F/'accepted-delivery.json').exists():
 accepted=read(F/'accepted-delivery.json');profile=read(ROOT/'channels/native-skill-source-runtime-accepted-20261028-v1.json')
 assert accepted['ok']and accepted['source_metadata_delivery_complete']and not accepted['full_attribute_delivery']
 assert accepted['own_locks_released']and not accepted['player_database_restore']
 for ch in ('online','local'):
  assert accepted['channels'][ch]['observation_seconds']>=120
  assert profile['channels'][ch]['files']==c['channels'][ch]['files']
  plan(ROOT,profile,ch)
print(json.dumps(dict(ok=True,channels=2,existing_inverse_leaves=13,new_modules=6,all_other_sources_preserved=True,attribute_delivery_admitted=False,client_changes=0,new_hooks=0)))
