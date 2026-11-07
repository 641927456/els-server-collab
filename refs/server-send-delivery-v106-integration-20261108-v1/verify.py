"""Verify the exact composed delivery, retaining accepted V106 native CP/banner."""
import ast,hashlib,json,subprocess,sys
from pathlib import Path
A=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
b=read(A/'bindings.json');previous=read(A/b['previous'])['effective_source_files']
actual={p.relative_to(A/'source').as_posix():sha(p)for p in(A/'source').rglob('*.py')}
assert len(actual)==30 and actual==b['source_files']
assert {n for n in actual if actual[n]!=previous[n]}==set(b['changed_from_previous'])
assert len(b['changed_from_previous'])==3
for n,v in b['parent_files'].items():assert sha(A/'parent'/n)==v
for n,v in b['portable_tests'].items():assert sha(A/n)==v
r=read(A/'parent-retention.json')
assert r['previous_source_files']==previous and r['current_source_files']==actual
assert r['unaffected_owned_modules_exact']==27 and r['property_tests_passed']==3
assert len(r['accepted_incoming_files'])==10 and r['original_CP_handler_and_peer_appearance_function_exact']
def function(path,name):
 return next(n for n in ast.parse(path.read_bytes()).body if isinstance(n,ast.FunctionDef)and n.name==name)
for name in ['handle','_appearance_changed']:
 assert ast.dump(function(A/'source/els_server/domain/achievement_flow.py',name))==ast.dump(function(A/'parent/els_server/domain/achievement_flow.py',name))
for f in ['native-clock.json','native-metadata.json','native-scene.json','native-notebook.json']:
 q=read(A/f);assert q['ok']
 assert {k.split('/',1)[1]:v for k,v in q['source'].items()}==actual
 if 'checks'in q:assert all(q['checks'].values())
 if 'GIL_enabled'in q:assert q['GIL_enabled']is False
 if 'owned_runtime_removed'in q:assert q['owned_runtime_removed']and not q['connections']and not q['errors']
q=read(A/'native-scene.json');assert q['counts']==dict(clock_after_B3=3,deaths=45,fresh_pickups=45,rooms=3,clock_after_BB=3)and q['cold_currency_equals_ACK']
signed=read(A/'signed-selection.json');endpoint=read(A/'compiled-endpoint.json')
assert signed['ok']and signed['version']==107 and signed['actual_prior_version']==106
assert signed['components_verified']==2877 and signed['selected_source_files']==30 and signed['selected_template_configs']==2
assert signed['repeat_downloads']==signed['upgrade_repeat_downloads']==0 and not signed['upgrade_full_archive_downloaded']
assert signed['upgrade_first']['reused_files']==2845 and signed['upgrade_first']['downloaded_files']==32
assert signed['original_EXE_KOM_changes']==0 and not signed['game_started']
assert endpoint['passed']and endpoint['normal_stop']and endpoint['owned_workspace_removed']
assert all(signed['source'][n]==v for n,v in actual.items())
files=read(A/'delivery-files.json')['files'];assert len(files)==32
assert {r['path']:r['sha256']for r in files}==signed['source']
assert sum(r['parent_sha256']is None for r in files)==2
reference=read(A/'resource-reference.json');assert reference['seconds']==60 and reference['diagnostic_only']and not reference['capacity_qualified']
assert not b['installed']and not b['public_capacity_qualified']
subprocess.run([sys.executable,'-B',str(A/'test_guild47_plan.py'),'-v'],check=True)
print(json.dumps(dict(ok=True,source_files=30,accepted_parent_features_retained=10,oracle_generated_cases=400,explicit_boundary_examples=3,signed_components=2877,production_installed=False,public_capacity_qualified=False)))
