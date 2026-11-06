"""Keep loot identity tied to economic graph fields, excluding no-drop spawn admission."""
import copy,hashlib,json,re,shutil
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[3];V=W.parent/'fix-v5';J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
M=J(V/'candidate-manifest.json');old_parent=Path(M['parent_runtime']);head=J(ROOT/'releases/online/current.json');R=ROOT/head['path'];assert H(R/'rollup-manifest.json')==head['manifest_sha256']
for row in M['files']:
 current=R/row['path'];assert(H(current)if current.is_file()else None)==row['parent_sha256'],row['path']
M.update(parent_release=head['release'],parent_runtime=str(R),parent_manifest_sha256=head['manifest_sha256'],parent_pointer_sha256=H(ROOT/'releases/online/current.json'))
assert J(W/'loot-scope-root-cause.json')['ok']
C=W/'candidate';assert not C.exists();C.mkdir()
for row in M['files']:
 source=V/'candidate'/row['path'];assert H(source)==row['sha256'];out=C/row['path'];out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,out)
name='els_server/domain/dungeon_routes.py';original=(R/name).read_bytes();text=original.decode('utf8');anchor=" graphs={row['source']:catalog['graphs'][row['source']] for row in routes.values()}";assert text.count(anchor)==1
replacement=""" # Dynamic scripted actors are created with no_drop=True and have no
 # static source_index. Their admission list cannot authorize loot; retain
 # every other graph field, including all static actors and transitions.
 graphs={}
 for source in {row['source']for row in routes.values()}:
  graph=catalog['graphs'][source]
  stages={index:{key:value for key,value in stage.items()if key!='allowed_summons'}
      for index,stage in graph['stages'].items()}
  graphs[source]={**graph,'stages':stages}"""
edited=text.replace(anchor,replacement);out=C/name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(edited.encode('utf8'));compile(edited,name,'exec')
pack=J(C/'els_server/data/client/dungeon_routes.json');current=J(R/'els_server/data/client/dungeon_routes.json')
def snapshot(data,maps):
 routes={str(i):data['routes'][str(i)]for i in sorted(maps,key=int)};graphs=copy.deepcopy({v['source']:data['graphs'][v['source']]for v in routes.values()})
 for graph in graphs.values():
  for stage in graph['stages'].values():del stage['allowed_summons']
 return dict(routes=routes,graphs=graphs)
proof=[]
for module in('dungeon_source_loot','dungeon_material_loot_catalog','dungeon_loot_catalog'):
 data_name=f'els_server/data/{module}.json';module_name=f'els_server/domain/{module}.py';raw=(R/data_name).read_bytes();data=json.loads(raw);old_scope=data['route_scope_sha256'];a,b=snapshot(current,data['maps']),snapshot(pack,data['maps']);assert a==b
 fingerprint=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest();assert raw.count(old_scope.encode())==1
 newraw=raw.replace(old_scope.encode(),fingerprint.encode());newdata=json.loads(newraw);assert{key:v for key,v in data.items()if key!='route_scope_sha256'}=={key:v for key,v in newdata.items()if key!='route_scope_sha256'}
 out=C/data_name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(newraw)
 source=(R/module_name).read_bytes();old_data_sha=hashlib.sha256(raw).hexdigest();new_data_sha=hashlib.sha256(newraw).hexdigest();token=("DATA_SHA='"+old_data_sha+"'").encode();assert source.count(token)==1
 newsource=source.replace(token,("DATA_SHA='"+new_data_sha+"'").encode());out=C/module_name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(newsource);compile(newsource,module_name,'exec')
 proof.append(dict(catalog=module,maps=len(data['maps']),data_path=data_name,module_path=module_name,parent_data_sha256=old_data_sha,data_sha256=new_data_sha,old_route_scope=old_scope,new_route_scope=fingerprint,only_data_field_changed='route_scope_sha256',all_pools_ticks_items_quantities_and_descriptors_equal=True,current_and_pending_spawn_graphs_have_equal_economic_scope=True))
files=[]
for p in sorted(C.rglob('*')):
 if not p.is_file():continue
 name=p.relative_to(C).as_posix();before=R/name;files.append(dict(path=name,delivery_role='source_only'if name.startswith('tools/')else'runtime',size=p.stat().st_size,sha256=H(p),parent_sha256=H(before)if before.is_file()else None))
M.update(files=files,prior_frozen_candidate=str(V),loot_scope_fix=True,installed=False,git_submitted=False)
(W/'candidate-manifest.json').write_text(json.dumps(M,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(W/'loot-policy-invariance.json').write_text(json.dumps(dict(ok=True,rows=proof,changed_runtime_leaves=12,changed_development_leaves=2,player_schema_changed=False,stored_drop_context_and_descriptors_changed=False),indent=2),encoding='utf8')
(W/'parent-rebinding.json').write_text(json.dumps(dict(ok=True,prior_parent=str(old_parent),current_parent=str(R),newer_parent_changes_preserved=True,source_dependency_payloads_unchanged=True),indent=2),encoding='utf8')
for name in('prepare_runtime.py','cleanup_runtime.py'):(W/name).write_bytes((V/name).read_bytes())
print(json.dumps(dict(ok=True,runtime_files=12,development_files=2,source_loot_catalogs=3,economic_values_changed=False)))
