"""Verify the three-leaf runtime boundary independently from pending attribute code."""
from pathlib import Path
import ast,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import plan
read=lambda p:json.loads(p.read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest()
F=ROOT/'references/native-skill-boundary-20261028-v1';d=read(F/'delta.json')
p=read(ROOT/d['parent']);c=read(ROOT/'channels/native-skill-boundary-20261028-v1.json');m=read(F/'manifest.json')
patches={
 'els_server/domain/skill_state.py':[(b"if (character or {}).get('force_inventory'):",b'if character is not None:')],
 'els_server/domain/ordinary_skill_pages.py':[(b"fixed+=vectors(character)if character.get('force_inventory')else bytes(8)",b'fixed+=vectors(character)')],
 'els_server/domain/owned_growth_items.py':[(b'        register()\r\n',b'        register()\r\n        from els_server.domain.boosting_2026_force_extraction import register as register_extraction\r\n        register_extraction()\r\n')],
}
assert m['existing_runtime_leaves']==3 and m['attribute_delivery_admission']is False
assert all(m[k]==0 for k in('new_runtime_modules','new_tables','install_DDL','client_files','new_hooks'))
for channel in('online','local'):
 old={r['path']:r for r in p['channels'][channel]['files']};rows={r['path']:r for r in c['channels'][channel]['files']}
 assert rows.keys()==old.keys() and {n for n in rows if rows[n]!=old[n]}==patches.keys()
 assert set(d['channels'][channel])==patches.keys()
 for key in('retained_client_sources','retained_client_support_sources','retained_signed_launcher_sha256','retained_signed_payload_sha256'):
  assert p['channels'][channel].get(key)==c['channels'][channel].get(key)
 for path,changes in patches.items():
  parent=(ROOT/old[path]['source']).read_bytes();raw=(ROOT/rows[path]['source']).read_bytes()
  assert sha(parent)==old[path]['sha256']==d['channels'][channel][path]['before_sha256']
  expected=parent
  for before,after in changes:assert expected.count(before)==1;expected=expected.replace(before,after)
  assert expected==raw and sha(raw)==rows[path]['sha256']==d['channels'][channel][path]['sha256']
  assert len(raw)==rows[path]['size'];ast.parse(raw)
  assert all(word not in raw for word in(b'native_skill_production',b'native_attribute',b'Interceptor.',b'Memory.write'))
 plan(ROOT,c,channel)
dep=m['unchanged_relative_dependency'];raw=(F/dep['path']).read_bytes()
assert sha(raw)==dep['sha256'] and dep['runtime_delta']is False
if (F/'accepted-delivery.json').exists():
 accepted=read(F/'accepted-delivery.json');profile=read(ROOT/'channels/native-skill-boundary-accepted-20261028-v1.json')
 assert accepted['ok']and accepted['three_leaf_delivery_complete']and not accepted['whole_user_goal_complete']and not accepted['full_attribute_delivery']
 assert accepted['own_locks_released']and not accepted['player_database_restore']and accepted['new_or_expanded_game_hooks']==accepted['new_client_files']==0
 assert all(accepted['channels'][ch]['observation_seconds']>=120 and accepted['channels'][ch]['changed_existing_files']==3 for ch in('online','local'))
 assert profile['source_Git_head']==accepted['source_Git_head']and profile['source_PR']==606
 assert all(profile['channels'][ch]['files']==c['channels'][ch]['files']for ch in('online','local'))
 for ch in('online','local'):plan(ROOT,profile,ch)
print(json.dumps(dict(ok=True,existing_runtime_leaves=3,channels=2,whole_byte_source_inverse=True,client_changes=0,new_hooks=0,attribute_delivery_admitted=False)))
