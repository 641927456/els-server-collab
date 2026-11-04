"""All actual economic loaders accept spawn-only edits and reject static changes."""
import copy,json,sys
from pathlib import Path
W=Path(__file__).resolve().parent;sys.dont_write_bytecode=True;sys.path.insert(0,str(W/'runtime'))
from els_server.domain import dungeon_routes as routes,dungeon_source_loot as source,dungeon_material_loot_catalog as material,dungeon_loot_catalog as normal
data=routes.route_catalog()._data;rows=[]
for module in(source,material,normal):
 c=module.catalog();maps=c['maps'];base=routes.loot_scope_sha256(maps);assert base==c['route_scope_sha256']
 selected={data['routes'][str(i)]['source']for i in maps};saved={k:copy.deepcopy(data['graphs'][k])for k in selected}
 try:
  for name in selected:
   for stage in data['graphs'][name]['stages'].values():stage['allowed_summons']=[2147483647]
  module.catalog.cache_clear();assert module.catalog()and routes.loot_scope_sha256(maps)==base
 finally:
  data['graphs'].update(copy.deepcopy(saved));module.catalog.cache_clear()
 name=sorted(selected)[0];graph=data['graphs'][name];stage=next(iter(graph['stages'].values()));part=next(iter(stage['parts'].values()))
 changes=[(graph,'source_sha256','f'*64),(part,'conditions',[]),(part,'groups',[])]
 for owner,key,value in changes:
  old=owner[key];owner[key]=value;assert routes.loot_scope_sha256(maps)!=base
  module.catalog.cache_clear()
  try:module.catalog()
  except ValueError:pass
  else:raise AssertionError((module.__name__,key,'static edit accepted'))
  finally:owner[key]=old;module.catalog.cache_clear()
 assert module.catalog()
 rows.append(dict(catalog=module.__name__,maps=len(maps),spawn_only_change_accepted=True,static_source_transition_population_changes_rejected=3))
out=dict(ok=True,rows=rows,live_files_mutated=False,economic_loader_validation_retained=True)
(W/'actual-scope-tests.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8');print(json.dumps(out))
