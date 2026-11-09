"""Independent read-only candidate checks; no game, player DB or deployment."""
from pathlib import Path
import ast,collections,hashlib,json,sys
R=Path('G:/els');H=Path(__file__).resolve().parent;m=json.loads((H/'candidate.json').read_bytes());C=Path(m['source']);B=R/m['parent']['path'];SHA=lambda b:hashlib.sha256(b).hexdigest();checks={}
for row in m['files']:
 raw=(C/row['path']).read_bytes();assert SHA(raw)==row['sha256'];old=B/row['path'];assert(SHA(old.read_bytes())if old.exists()else None)==row['parent_sha256']
 if row['path'].endswith('.py'):ast.parse(raw)
checks['leaves']=len(m['files']);checks['changed_leaves']=sum(r['sha256']!=r['parent_sha256']for r in m['files'])
d=json.loads((C/'els_server/data/retained_box_openings.json').read_bytes());outputs={r['template']:r for r in d['outputs']};boxes={r['template']:r for r in d['boxes']};assert len(outputs)==len(d['outputs'])and len(boxes)==len(d['boxes']);assert 136186 not in boxes and 136186 not in outputs and 136055 not in outputs
branches=[b for r in boxes.values()for b in r.get('branches',())];assert len(branches)==853
for t,r in boxes.items():
 assert type(r['minimum_level'])is int and r['minimum_level']>=0
 for b in r.get('branches',()):
  assert(b['key']==0 or b['key_count']>0)and type(b['key_count'])is int and b['key_count']>=0 and b['key']!=t
  assert b['outputs']and len({o['template']for o in b['outputs']})==len(b['outputs'])
  for o in b['outputs']:assert o['template']in outputs and type(o['quantity'])is int and o['quantity']>0 and type(o['weight'])is int and o['weight']>0 and type(o.get('inventory_days',0))is int and o.get('inventory_days',0)>=0
checks['finite_reward_data']=dict(boxes=len(boxes),outputs=len(outputs),branches=len(branches),frozen_136186_absent=True,current_ticket_136055_not_reopened=True,source_key_collision=False)
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(B/'vendor'),str(R/'tools/pylibs')]
import els_server.domain,els_server.storage,els_server.protocol
for package,part in((els_server.domain,'domain'),(els_server.storage,'storage'),(els_server.protocol,'protocol')):package.__path__.insert(0,str(C/'els_server'/part))
from els_server.domain.owned_growth_items import install
install()
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
from els_server.domain.retained_box_openings import catalog
assert catalog()['boxes']==d['boxes']
from els_server.domain.item_expiration import validate
for days in {o.get('inventory_days',0)for b in branches for o in b['outputs']}:validate(1794038400+days*86400)
for t,o in outputs.items():assert(VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t],TEMPLATE_MAX_STACKS[t])==(o['metadata'],o['group'],o['max_stack']),(t,'reader tuple')
checks['all_output_reader_tuples_match_runtime']=len(outputs)
from els_server.domain.acquisition_policy import can_acquire
new=[r for r in d['outputs']if r['new_reader']or r.get('new_acquisition')]
for r in new:assert can_acquire(r['template'])is False,('Unexpected generic acquisition',r['template'])
checks['new_acquisition_templates_require_exact_source']=len(new)
from els_server.domain.equipment_requirements import catalog as class_catalog
scope=0
for t,r in boxes.items():
 for cls,info in class_catalog()[0].items():
  for side in range(2 if info['family']==10 else 1):
   matched=[b for b in r.get('branches',())if('families'not in b or info['family']in b['families'])and('classes'not in b or cls in b['classes'])and('active_unit'not in b or b['active_unit']==side)]
   assert len(matched)==len({b['key']for b in matched}),('Overlapping rules',t,cls,side);scope+=len(matched)
checks['unambiguous_actual_class_key_side_combinations']=scope
profile=next(p for p in json.loads((C/'tools/client_compatibility_profiles.json').read_bytes())['profiles']if p['id']=='cn-dx11-6c6b5180')
for name,pin in profile['artifacts'].items():
 path=C/name if(C/name).exists()else B/name;assert SHA(path.read_bytes())==pin,name
checks['compatibility_artifacts_match']=len(profile['artifacts'])
spec=json.loads((C/'tools/owned_box_key_aliases.json').read_bytes());aliases=0
for r in spec['rules']:
 for old,newkey in r['aliases'].items():assert boxes[r['template']]['key_aliases'][old]==newkey and newkey in VERIFIED_TEMPLATES;aliases+=1
checks['native_key_aliases_match_server']=dict(boxes=len(spec['rules']),aliases=aliases)
virtual={p.relative_to(B).as_posix():p for p in(B/'els_server').rglob('*.py')};virtual.update({r['path']:C/r['path']for r in m['files']if r['path'].startswith('els_server/')and r['path'].endswith('.py')});calls=collections.defaultdict(list)
for relative,path in virtual.items():
 tree=ast.parse(path.read_bytes());imports={}
 for node in ast.walk(tree):
  if isinstance(node,ast.ImportFrom):
   for entry in node.names:imports[entry.asname or entry.name]=(node.module,entry.name)
 for node in ast.walk(tree):
  if not isinstance(node,ast.Call)or not isinstance(node.func,ast.Name):continue
  origin=imports.get(node.func.id)
  if origin in{('els_server.domain.cubes','opening_count'),('els_server.storage.fixed_cubes','open_cube'),('els_server.storage.consumables','use'),('els_server.domain.acquisition_policy','can_acquire')}:calls['.'.join(origin)].append(dict(path=relative,line=node.lineno))
checks['static_direct_callsites']=dict(calls)
report=dict(ok=True,checks=checks,source_pins=m['files'],candidate_manifest_sha256=SHA((H/'candidate.json').read_bytes()),parent_manifest_sha256=SHA((B/'rollup-manifest.json').read_bytes()),player_save_access=False,network=False,game_process_access=False,source_writes=False)
(H/'independent-review-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(dict(ok=True,checks={k:v for k,v in checks.items()if k!='static_direct_callsites'},calls={k:len(v)for k,v in calls.items()})))
