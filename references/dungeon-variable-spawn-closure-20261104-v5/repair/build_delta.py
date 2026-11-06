import collections,copy,hashlib,importlib.util,json,math,statistics,struct,sys
from pathlib import Path
from constant_calls import trace
from flow_sources import Flow
W=Path(__file__).resolve().parent;ROOT=W.parents[3];C=W/'candidate';J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
head=J(ROOT/'releases/online/current.json');R=ROOT/head['path'];sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(ROOT/'tools'),str(W.parents[1]/'remaining-v4')]
from els_server.game_data import client_data,CLIENT_SHA
from scope import original,kl,tables
sp=importlib.util.spec_from_file_location('candidate_builder',C/'tools/build_dungeon_routes.py');b=importlib.util.module_from_spec(sp);sp.loader.exec_module(b)
verified=b.verified_ai_sources(ROOT,CLIENT_SHA);data=client_data();enums=data.resource('Enum.lua')
routes=J(R/'els_server/data/client/dungeon_routes.json');formal=J(R/'els_server/data/formal_npc_hp.json');raid=J(R/'els_server/data/raid_npc_hp.json')
manifest=J(R/'els_server/data/client/dungeon_routes.manifest.json');hm=J(R/'els_server/data/formal_npc_hp.manifest.json')
reference_path=ROOT/'analysis/monster-economy-formal-20261025-v1/raid-audit-v1/public-raid-hp-reference.json';assert H(reference_path)==raid['public_reference_sha256'];reference=J(reference_path);audit=J(reference_path.parent/'current-raid-audit.json')
raw_names={r['id']:r for r in J(ROOT/'analysis/dungeon-chain-20261015/native-npc-strings.json')['entries']}
cache={};gaps={};pins={};components={}
index_directory=ROOT/'analysis/npc-client-native-values-20261025-v1/continuation-v2'
original_names={r['Name'].lower()for name in('current-index.json','global-resource-index.json')for r in J(index_directory/name)['rows']}
def source(tid):
 definition=data.npc(tid);p,_=original(definition['script']);sha=H(p)
 previous=manifest['source_sha256'].get(p.name)
 assert previous in(None,sha),(tid,'source drift')
 if p.name.lower()in verified:assert H(verified[p.name.lower()])==sha
 manifest['source_sha256'][p.name]=sha;pins[tid]=dict(script=p.name,sha256=sha,path=str(p))
 return p,definition
def dependencies(tid):
 if tid in cache:return cache[tid]
 try:p,_=source(tid)
 except (AssertionError,KeyError,FileNotFoundError)as exc:gaps[tid]=repr(exc);cache[tid]=[];return []
 dump=kl.read(p.read_bytes());calls,unknown=trace(dump,enums)
 if unknown:
  with(W/'build-flow-progress.private.jsonl').open('a',encoding='utf8')as log:log.write(json.dumps(dict(template=tid,script=p.name,phase='flow-start',traced=len(cache)))+'\n')
  flow=Flow(dump,enums);analysis={(c['prototype'],c['call_pc']):c for c in flow.spawn_results()}
  with(W/'build-flow-progress.private.jsonl').open('a',encoding='utf8')as log:log.write(json.dumps(dict(template=tid,phase='flow-end',nodes=len(flow.nodes)))+'\n')
  for witness in unknown:
   result=analysis[witness['prototype'],witness['call_pc']]
   for resolved_target in result['targets']:
    calls.append(dict(witness,target=resolved_target,origin='finite_source_enum_flow',identity_witnesses=[r for r in result['identity_witnesses']if r[1]==resolved_target]))
 target=b.special_riding_target(dump,enums)
 if target is not None:calls.append(dict(prototype=dump['root'],call_pc=None,method='INIT_SPECIAL_RIDING_TARGET',target=target,target_definition_pc=None))
 cache[tid]=[dict(producer=tid,script=p.name,sha256=H(p),**c)for c in calls]
 if unknown:gaps[tid]=dict(unresolved_calls=unknown)
 return cache[tid]
def metadata(tid):
 if str(tid)in routes['npcs']:return
 definition=data.npc(tid);p=None
 if definition['script'].lower()not in original_names:
  # Original registration and initializer strings are present, but no such
  # Lua entry exists in the complete pinned archives. Preserve that original
  # identity; never borrow another mode's script or claim recovered MAX_HP.
  maximum=None;components[tid]=dict(MAX_HP=None,source='registered_native_identity_without_original_Lua_entry')
 else:
  p,definition=source(tid);dump=kl.read(p.read_bytes());root=dump['prototypes'][dump['root']]
  end=next(i+1 for i,x in enumerate(root['instructions'])if x[0]==63 and root['kgc'][x[2]|x[3]<<8]=='INIT_COMPONENT')
  view=copy.deepcopy(dump);view['prototypes'][view['root']]['instructions']=root['instructions'][:end]
  component=tables(view)['INIT_COMPONENT'];maximum=component.get('MAX_HP');assert maximum is None or(type(maximum)in(int,float)and math.isfinite(maximum)and maximum>0)
 record=raw_names[tid];assert record['verified_id']==tid;strings=[r['text']for r in record['strings']];assert strings[2].lower()==definition['script'].lower()
 routes['npcs'][str(tid)]=dict(strings=strings+['',''],script_max_hp=maximum,local_hp=maximum)
 identity={k:definition[k]for k in('enum','script','class_id','is_npc')};identity['script']=identity['script'].lower();assert str(tid)not in formal['templates']
 formal['templates'][str(tid)]=dict(**identity,source='current_client_explicit'if maximum is not None else'server_local_region_role_model',**({'fixed':maximum}if maximum is not None else{}))
 if p:components[tid]=dict(MAX_HP=maximum,source_sha256=H(p))
new_metadata=[];proofs=[];paths=[];edges=[];bindings=[];required=collections.defaultdict(set)
# Only source graphs used by an admitted route; start at actual static alternatives.
for name,graph in routes['graphs'].items():
 mids=[int(k)for kind in('routes','internal_routes','event_routes')for k,v in routes[kind].items()if v['source']==name]
 if not mids:continue
 additions={}
 for stage,s in graph['stages'].items():
  roots={n['template']for part in s['parts'].values()for group in part['groups']for parent in group['npcs']for n in parent.get('options',[parent])};pending=list(roots);seen=set(roots);parents={}
  while pending:
   producer=pending.pop()
   for edge in dependencies(producer):
    tid=edge['target']
    if tid in seen:continue
    seen.add(tid);pending.append(tid);parents[tid]=edge
  missing=seen-set(s['allowed_summons'])
  if not missing:continue
  s['allowed_summons']=sorted(set(s['allowed_summons'])|missing);additions[int(stage)]=sorted(missing)
  for tid in sorted(missing):
   chain=[];cursor=tid
   while cursor not in roots:edge=parents[cursor];chain.insert(0,edge);cursor=edge['producer']
   assert all(e['method'].lower()in('createnpcreq_lua','createnpchostreq_lua','init_special_riding_target')for e in chain)
   for mid in mids:
    paths.append(dict(dungeon=mid,source=name,stage=int(stage),target=tid,root=cursor,edges=chain));required[mid].add(tid)
    edges.append(dict(dungeon=mid,stage=int(stage),source=name,**chain[-1]))
   if str(tid)not in routes['npcs']:metadata(tid);new_metadata.append(tid)
   if data.npc(tid)['script'].lower()in original_names:source(tid)
 if additions:
  for mid in mids:proofs.append(dict(dungeon=mid,source=name,graph_sha256=graph['source_sha256'],stage_additions=additions))
# Preserve every existing binding. Add only mode-specific missing initialization.
for mid,targets in required.items():
 if str(mid)not in raid['maps']:continue
 row=raid['maps'][str(mid)];ref=reference['maps'][str(mid)];old=next(r for r in audit['rows']if r['map']==mid)
 assert ref['reference_level_matches']and old['graph_sha256']==row['graph_sha256']
 roles=collections.defaultdict(set)
 for actor in old['actors']:roles[actor['template']].add(bool(actor['boss']))
 pools={role:{tid:ref['templates'][str(tid)]['initial_HP_float32']for tid,flags in roles.items()if flags=={role}and str(tid)in ref['templates']}for role in(False,True)};assert pools[True]
 for tid in sorted(targets):
  if str(tid)in row['templates']:continue
  native=routes['npcs'][str(tid)];identity={k:formal['templates'][str(tid)][k]for k in('enum','script','class_id','is_npc')};explicit=native['script_max_hp']
  if explicit is not None:kind='current_client_explicit';value=explicit;extra={}
  elif str(tid)in ref['templates']:
   v=ref['templates'][str(tid)];kind='public_estimate_adopted_local_reference';value=v['initial_HP_float32'];extra={k:v[k]for k in('source_url','capture_sha256','reference_HP','public_name')}
  else:
   role=next(iter(roles[tid]))if len(roles[tid])==1 else False;pool=pools[role]or pools[True];value=statistics.median(pool.values());kind='local_same_mode_unique_role_median';extra=dict(role='boss'if role else'ordinary_or_dynamic',anchor_templates=sorted(pool),anchor_values={str(k):v for k,v in pool.items()},median_before_float32=value)
  hp=struct.unpack('<f',struct.pack('<f',value))[0];row['templates'][str(tid)]=dict(template=tid,**identity,hp=hp,source=kind,**extra);bindings.append(dict(dungeon=mid,template=tid,hp=hp,source=kind))
def write(name,value):
 p=C/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8');return p
raid['counts']=dict(collections.Counter(v['source']for m in raid['maps'].values()for v in m['templates'].values()))
rp=write('els_server/data/raid_npc_hp.json',raid);formal['sources']['raid_local_policy']=H(rp)
route=write('els_server/data/client/dungeon_routes.json',routes);manifest['payload_sha256']=H(route);write('els_server/data/client/dungeon_routes.manifest.json',manifest)
hp=write('els_server/data/formal_npc_hp.json',formal);hm['payload_sha256']=H(hp);write('els_server/data/formal_npc_hp.manifest.json',hm)
files=[dict(path=p.relative_to(C).as_posix(),delivery_role='source_only'if p.relative_to(C).parts[0]=='tools'else'runtime',size=p.stat().st_size,sha256=H(p),parent_sha256=H(R/p.relative_to(C))if(R/p.relative_to(C)).is_file()else None)for p in sorted(C.rglob('*'))if p.is_file()]
out=dict(parent_release=head['release'],parent_runtime=str(R),parent_manifest_sha256=H(R/'rollup-manifest.json'),client_sha256=CLIENT_SHA,files=files,qualified_maps=proofs,qualified_edges=edges,dependency_paths=paths,new_native_metadata=sorted(new_metadata),new_HP_identities=sorted(new_metadata),new_mode_HP_bindings=bindings,components=components,source_index_entries=len(verified),installed=False)
(W/'candidate-manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(W/'source-qualification.private.json').write_text(json.dumps(dict(scripts_traced=len(cache),pins=pins,unresolved=gaps),ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(dict(ok=True,maps=len(proofs),stage_targets=len(paths),new_metadata=new_metadata,bindings=len(bindings),scripts_traced=len(cache),unresolved_scripts=len(gaps))))
