"""Archive-only integrity/scope check; does not run Application, TLS or Game."""
from pathlib import Path
import argparse,hashlib,json,ast
O=Path(__file__).resolve().parent;ROOT=O.parents[1];J=lambda p:json.loads(p.read_bytes());H=lambda b:hashlib.sha256(b).hexdigest()
ap=argparse.ArgumentParser();ap.add_argument('--parent-config',type=Path);a=ap.parse_args()
c=J(O/'source-contract.json');assert c['candidate']and not c['activation']and not c['runtime_acceptance']
p=a.parent_config or ROOT/c['logical_archive_parent']['source'];b=p.read_bytes();assert H(b)==c['logical_archive_parent']['sha256'];parent=json.loads(b)['rules']
f=c['files'][0];p=ROOT/f['source'];assert p.resolve().is_relative_to(O.resolve());b=p.read_bytes();assert H(b)==f['sha256']and len(b)==f['size'];target=json.loads(b)['rules']
for e in c['evidence']:
 p=ROOT/e['path'];assert p.resolve().is_relative_to(O.resolve())and H(p.read_bytes())==e['sha256']
addition=J(O/'rule-additions.json');q=J(O/'qualified-additions.json');key=lambda r:(r['dungeon'],r['stage'],r['part'],r.get('trigger',r.get('activation')))
assert len(parent)==108 and len(addition)==18 and len(target)==126 and target==parent+addition and len({key(r)for r in target})==126
assert len(q)==18 and {key(x['rule'])for x in q}=={key(r)for r in addition}
assert sum(r['native_loop']for r in addition)==12 and all(type(r['npc_template'])is int and r['npc_template']>0 for r in addition)
for x in q:assert x['rule']in addition and x['native_action']['TRIGGER_ID']==x['rule']['trigger']and x['native_action']['TRIGGER_LOOP']==x['rule']['native_loop']
for m in ['online','local']:
 t=J(O/('server-TLS-'+m+'.json'));assert t['ok']and t['actual_Application_TLS']and len(t['cases'])==18 and {key(r)for r in t['cases']}=={key(r)for r in addition}and len(t['negative_cases'])==18 and t['native_loop_contexts']==12
 assert t['non_loop_duplicate_ACK_only']and t['no_HP_defeat_room_or_inventory_change']and not t['natural_clear']
t=J(O/'application-admissions.json');assert t['ok']and len(t['records'])==18 and all(r['normal_admission']and r['controlled_room']for r in t['records'])
assert t['source_overall_two_method_run_passed']is False and t['corrected_named_retirement_result']['errors']==[]


rc=J(O/'retirements/source-contract.json');f=rc['files'][0];b=(ROOT/f['source']).read_bytes();assert H(b)==f['sha256']and len(b)==f['size']
t=ast.parse(b);last=t.body[-1];assert isinstance(last,ast.Expr)and isinstance(last.value,ast.Call)and isinstance(last.value.func,ast.Attribute)and last.value.func.attr=='extend'and getattr(last.value.func.value,'id',None)=='RULES'
extra=ast.literal_eval(last.value.args[0]);assert extra==J(O/'retirements/rule-additions.json')and len(extra)==4
prior=ast.Module(body=t.body[:-1],type_ignores=[]);assert H(ast.dump(prior,include_attributes=False).encode())==rc['preserved146_parent_AST_sha256']
five=lambda r:(r['dungeon'],r['stage'],r['part'],r['template'],r['source']['source_index'])
assert {five(r)for r in extra}=={(34630,2,0,8147,8),(34640,0,0,8078,10),(34640,2,0,8079,2),(35310,0,0,9412,1)}
for r in extra:assert r['units']==([15]if r['template']==9412 else[14])and r['requires_native_255']and r['quest_independent']and not r.get('allow_combat_death')
for m in ['online','local']:
 app=J(O/('retirements/application-'+m+'.json'));tls=J(O/('retirements/server-TLS-'+m+'.json'))
 assert app['ok']and not app['errors']and not app['failures']and len(app['records'])==4 and sum(len(x['negative_cases'])for x in app['records'])==20
 assert tls['ok']and tls['actual_private_Application_TLS']and len(tls['cases'])==4
n=J(O/'retirements/native-source-qualification.json');assert n['passed']and len(n['rows'])==4 and n['class103_or_IS_NPC_false_not_globally_admitted']
for r in n['rows']:assert r['native_expiry']['flag']==255 and r['native_expiry']['status']==1 and r['native_expiry']['source']==r['native_expiry']['killer']==2**64-1
g=J(O/'retirements/gate-result.json');assert len(g['rows'])==4 and all(r['other_actors_unchanged']for r in g['rows'])
assert next(r for r in g['rows']if r['template']==9412)['after_accepted_fact']==[False]
print(json.dumps(dict(ok=True,runtime_files=2,activation_rules126=True,retirement_rules150=True,added_activation18=True,added_retirement4=True,old108_and146_preserved=True,recorded_retirement_App_each4_and_negative20=True,recorded_retirement_TLS_each4=True,old_source_matrix_or_Game_rerun=False)))
