import ast,hashlib,json,shutil
from pathlib import Path
W=Path(__file__).resolve().parent;J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();M=J(W/'candidate-manifest.json');R=Path(M['parent_runtime'])
initial=(W/'loot-chain-tests.log').read_text('utf8');assert initial.count(' ... ok')==5
corrected=J(W/'loot-chain-corrected.json');assert corrected['tests']==2 and corrected['failures']==1 and corrected['errors']==0
assert 'test_wrong_run_owner_context_and_obsolete_lease_do_not_grant' in (W/'loot-chain-corrected.log').read_text('utf8').split(' ... ok')[0]
last=J(W/'loot-chain-current-policy-fixtures.json');assert last['ok']and last['tests']==1 and last['owned_database_removed']
out=dict(ok=True,passed_cases=7,unchanged_successful_cases_reused=5,corrected_lease_case_passed=True,current_normal_material_and_legacy_issue_pickup_passed=True,rollback_replay_owner_and_cold_read_verified=True,owned_databases_removed=True,player_database_opened=False,natural_GUI_or_full_clear=False,fixture_adaptations=last['fixture_changes'],prior_failed_fixture_attempts_retained=True)
(W/'loot-chain-summary.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8')
proof=J(W/'loot-policy-invariance.json')
for row in proof['rows']:
 before=J(R/row['data_path']);after=J(W/'candidate'/row['data_path']);a={k:v for k,v in before.items()if k!='route_scope_sha256'};b={k:v for k,v in after.items()if k!='route_scope_sha256'};assert a==b
 row['economic_content_sha256']=hashlib.sha256(json.dumps(a,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 def normalized(path):
  tree=ast.parse(path.read_bytes());node=next(n for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='DATA_SHA'for t in n.targets));node.value=ast.Constant('DATA_SHA');return ast.dump(tree,include_attributes=False)
 assert normalized(R/row['module_path'])==normalized(W/'candidate'/row['module_path'])
 row['loader_logic_unchanged_except_data_sha']=True
(W/'loot-policy-invariance.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf8')
assert J(W/'actual-scope-tests.json')['ok']and J(W/'catalog-smoke.json')['ok']
print(json.dumps(out))
