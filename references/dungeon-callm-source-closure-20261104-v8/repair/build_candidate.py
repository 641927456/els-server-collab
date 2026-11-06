"""Apply only shared-flow source-qualified missing dependencies to the actual parent."""
import collections,copy,hashlib,importlib.util,json,math,statistics,struct,sys
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[3];J=lambda p:json.loads(p.read_bytes());H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();closure=J(W/'full-source-closure.json');pointer=J(ROOT/'releases/online/current.json');R=ROOT/pointer['path'];C=W/'candidate';assert not C.exists();C.mkdir();assert H(R/'rollup-manifest.json')==pointer['manifest_sha256'];sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(ROOT/'tools'),str(ROOT/'analysis/dungeon-stalls-20261103-v1/remaining-v4')]
from els_server.game_data import client_data,CLIENT_SHA
from scope import original,kl,tables
data=client_data();routes=J(R/'els_server/data/client/dungeon_routes.json');formal=J(R/'els_server/data/formal_npc_hp.json');raid=J(R/'els_server/data/raid_npc_hp.json');manifest=J(R/'els_server/data/client/dungeon_routes.manifest.json');hm=J(R/'els_server/data/formal_npc_hp.manifest.json');raw={r['id']:r for r in J(ROOT/'analysis/dungeon-chain-20261015/native-npc-strings.json')['entries']};refpath=ROOT/'analysis/monster-economy-formal-20261025-v1/raid-audit-v1/public-raid-hp-reference.json';assert H(refpath)==raid['public_reference_sha256'];reference=J(refpath);audit=J(refpath.parent/'current-raid-audit.json');required=collections.defaultdict(set);components={};paths=copy.deepcopy(closure['paths']);edges=[]
for path in paths:
 for e in path['edges']:
  e['sha256']=e['source_sha256'];p,_=original(e['script']);assert H(p)==e['sha256'];prior=manifest['source_sha256'].get(p.name);assert prior in(None,e['sha256']);manifest['source_sha256'][p.name]=e['sha256']
 edges.append(dict(dungeon=path['dungeon'],stage=path['stage'],source=path['source'],**path['edges'][-1]));required[path['dungeon']].add(path['target'])
maps=[]
for row in closure['rows']:
 stage=routes['graphs'][row['source']]['stages'][str(row['stage'])];assert not set(row['missing'])&set(stage['allowed_summons']);stage['allowed_summons']=sorted(set(stage['allowed_summons'])|set(row['missing']))
 for mid in row['maps']:
  found=next((m for m in maps if m['dungeon']==mid),None)
  if found is None:found=dict(dungeon=mid,source=row['source'],graph_sha256=routes['graphs'][row['source']]['source_sha256'],stage_additions={});maps.append(found)
  found['stage_additions'][str(row['stage'])]=row['missing']
new=[]
for tid in sorted({p['target']for p in paths}):
 if str(tid)in routes['npcs']:continue
 definition=data.npc(tid);p,_=original(definition['script']);dump=kl.read(p.read_bytes());root=dump['prototypes'][dump['root']];end=next(i+1 for i,x in enumerate(root['instructions'])if x[0]==63 and root['kgc'][x[2]|x[3]<<8]=='INIT_COMPONENT');view=copy.deepcopy(dump);view['prototypes'][view['root']]['instructions']=root['instructions'][:end];component=tables(view)['INIT_COMPONENT'];maximum=component.get('MAX_HP');assert maximum is None or(type(maximum)in(int,float)and math.isfinite(maximum)and maximum>0)
 record=raw[tid];assert record['verified_id']==tid;strings=[r['text']for r in record['strings']];assert strings[2].lower()==definition['script'].lower();routes['npcs'][str(tid)]=dict(strings=strings+['',''],script_max_hp=maximum,local_hp=maximum);identity={k:definition[k]for k in('enum','script','class_id','is_npc')};identity['script']=identity['script'].lower();assert str(tid)not in formal['templates'];formal['templates'][str(tid)]=dict(**identity,source='current_client_explicit'if maximum is not None else'server_local_region_role_model',**({'fixed':maximum}if maximum is not None else{}));manifest['source_sha256'][p.name]=H(p);components[tid]=dict(MAX_HP=maximum,source_sha256=H(p));new.append(tid)
bindings=[]
for mid,targets in required.items():
 if str(mid)not in raid['maps']:continue
 row=raid['maps'][str(mid)];ref=reference['maps'][str(mid)];old=next(r for r in audit['rows']if r['map']==mid);assert ref['reference_level_matches']and old['graph_sha256']==row['graph_sha256'];roles=collections.defaultdict(set)
 for actor in old['actors']:roles[actor['template']].add(bool(actor['boss']))
 pools={role:{tid:ref['templates'][str(tid)]['initial_HP_float32']for tid,flags in roles.items()if flags=={role}and str(tid)in ref['templates']}for role in(False,True)}
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
raid['counts']=dict(collections.Counter(v['source']for m in raid['maps'].values()for v in m['templates'].values()));rp=write('els_server/data/raid_npc_hp.json',raid);formal['sources']['raid_local_policy']=H(rp);route=write('els_server/data/client/dungeon_routes.json',routes);manifest['payload_sha256']=H(route);write('els_server/data/client/dungeon_routes.manifest.json',manifest);hp=write('els_server/data/formal_npc_hp.json',formal);hm['payload_sha256']=H(hp);write('els_server/data/formal_npc_hp.manifest.json',hm)
files=[dict(path=p.relative_to(C).as_posix(),delivery_role='runtime',size=p.stat().st_size,sha256=H(p),parent_sha256=H(R/p.relative_to(C)))for p in sorted(C.rglob('*'))if p.is_file()];out=dict(parent_release=pointer['release'],parent_runtime=str(R),parent_manifest_sha256=pointer['manifest_sha256'],client_sha256=CLIENT_SHA,files=files,qualified_maps=maps,qualified_edges=edges,dependency_paths=paths,new_native_metadata=new,new_HP_identities=new,new_mode_HP_bindings=bindings,components=components,source_coverage_scripts=closure['scripts'],source_reconstruction_uses_shared_CFG_for_CALL_and_CALLM=True,installed=False)
(W/'candidate-manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(ok=True,modes=len(maps),stage_targets=len(paths),new_native_metadata=new,mode_HP_bindings=len(bindings),files=len(files))))
