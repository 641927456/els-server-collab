"""Compile captured native dungeon graphs; retain explicit unsupported reasons.
Combat HP/attack and solo branch choices are local play rules, not retail stats.
"""
import collections,hashlib,json,math,re,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from els_server.game_data import client_data,CLIENT_SHA
from read_kl_bytecode import read,initializer
from npc_spawn_source_flow import Flow
SOURCE=ROOT/'analysis/dungeon-chain-20261015'

def verified_ai_sources(root,client_sha):
 """Include later native decodes, bound to the same original client build."""
 directory=root/'analysis/npc-client-native-values-20261025-v1/continuation-v2'
 sources={}
 for line in (directory/'decode-ledger.jsonl').read_text(encoding='utf8').splitlines():
  row=json.loads(line);path=Path(row['path']);key=row['name'].lower()
  if row['client_sha256']!=client_sha or path.name.lower()!=key:raise ValueError('Native AI source identity')
  if hashlib.sha256(path.read_bytes()).hexdigest()!=row['plain_sha256']:raise ValueError('Native AI source checksum')
  if key in sources and sources[key].read_bytes()!=path.read_bytes():raise ValueError('Conflicting native AI sources')
  sources[key]=path
 return sources

def numbered(table,prefix):
 return sorted(((int(k[len(prefix):]),v) for k,v in table.items() if re.fullmatch(re.escape(prefix)+r'\d+',k)),key=lambda x:x[0])
def values(table):return [table[k] for k in sorted((k for k in table if str(k).isdigit()),key=int) if k!='0' and table[k] is not None]
def special_riding_target(dump,enums):
 """The native riding action creates the declared target outside CreateNPCReq."""
 root=dump['prototypes'][dump['root']]
 for index,(op,a,c,b) in enumerate(root['instructions']):
  if op!=0x3f or root['kgc'][c|(b<<8)]!='INIT_SPECIAL_RIDING_TARGET':continue
  fragment=json.loads(json.dumps(dump))
  fragment['prototypes'][fragment['root']]['instructions']=root['instructions'][:index+1]
  globals=dict(enums,TRUE=True,FALSE=False)
  target=initializer(fragment,globals)['INIT_SPECIAL_RIDING_TARGET']['TARGET_NPC_UNIT_ID']
  if type(target)is not int or target not in enums['NPC_UNIT_ID'].values():raise ValueError('Special riding NPC target identity')
  return target
 return None

def summon_targets(dump,enums):
 refs=set();target=special_riding_target(dump,enums)
 if target is not None:refs.add(target)
 for prototype in dump['prototypes']:
  tokens={v for v in prototype['kgc']if isinstance(v,str)}
  if not any('createnpcreq'in v.lower()or'createnpchostreq'in v.lower()for v in tokens):continue
  refs.update(enums['NPC_UNIT_ID'][token]for token in tokens if token.startswith('NUI_')and token in enums['NPC_UNIT_ID'])
 if any(any(isinstance(v,str)and v.lower()in('createnpcreq_lua','createnpchostreq_lua')for v in p['kgc'])for p in dump['prototypes']):
  for call in Flow(dump,enums).spawn_results():refs.update(call['targets'])
 return refs

def build():
 data=client_data();enums=data.resource('Enum.lua')
 script_globals=data.resource('DungeonEnum.lua');script_globals.update(TRUE=True,FALSE=False)
 captured=json.loads((SOURCE/'resource-manifest.json').read_text(encoding='utf8'))
 assert captured['client_sha256']==CLIENT_SHA
 raw_names={e['id']:e for e in json.loads((SOURCE/'native-npc-strings.json').read_text(encoding='utf8'))['entries']}
 resource_paths={p.name.lower():p for p in (SOURCE/'resources').glob('*.lua')}
 # Newer region scripts can be absent from the historical disk index. These
 # resources were decoded independently with the pinned native transform.
 extra=ROOT/'analysis/region-quests-20261015/ui'
 proof={r['name']:r for r in json.loads((extra/'proof.json').read_text(encoding='utf8'))}
 for p in extra.glob('Dungeon_*.lua'):
  if hashlib.sha256(p.read_bytes()).hexdigest()!=proof[p.name]['sha256']:raise ValueError('Native late dungeon identity')
  if p.name.lower() in resource_paths and resource_paths[p.name.lower()].read_bytes()!=p.read_bytes():raise ValueError('Conflicting dungeon sources')
  resource_paths[p.name.lower()]=p
 for key,path in verified_ai_sources(ROOT,CLIENT_SHA).items():
  if key in resource_paths and resource_paths[key].read_bytes()!=path.read_bytes():raise ValueError('Conflicting dungeon AI sources')
  resource_paths[key]=path
 scope_path=ROOT/'config/dungeon_scope.json';scope_raw=scope_path.read_bytes();scope=json.loads(scope_raw)
 policy_path=ROOT/'config/dungeon_local_rules.json';policy_raw=policy_path.read_bytes();policy=json.loads(policy_raw)['encounter_policy']
 if scope['schema_version']!=1 or scope['client_sha256']!=CLIENT_SHA:raise ValueError('Dungeon scope identity')
 npcs={};sources={};routes={};internal_routes={};issues={};npc_dependencies={}
 def resolve(value,group):
  if type(value) is int:return value
  if not isinstance(value,dict) or set(value)!={'global'}:raise ValueError('Unresolved '+group)
  prefix,key=value['global'].split('.',1)
  if prefix!=group or key not in enums[group]:raise ValueError('Unknown enum '+value['global'])
  return enums[group][key]
 def flag(group,key,default=False):
  v=group.get(key,default)
  # These source globals are absent from the captured environment. Lua's
  # assignment of nil removes the field, so use the same local spawn default
  # as an omitted property. Do not turn the misspellings into FALSE aliases.
  if isinstance(v,dict) and v.get('global') in ('FALS','FASLE') and v['global'] not in script_globals:v=default
  if v is None:v=default
  if type(v) is not bool:raise ValueError('Unresolved flag '+key)
  return v
 def npc(identity):
  if str(identity) in npcs:return
  record=raw_names.get(identity);definition=data.npc(identity)
  if record is None or record['verified_id']!=identity:raise ValueError('NPC absent from native snapshot '+str(identity))
  strings=[r['text'] for r in record['strings']]
  if strings[2].lower()!=(definition['script'] or '').lower():raise ValueError('NPC script identity mismatch '+str(identity))
  hp=5000 if definition['is_npc'] else 500
  component={};src=resource_paths.get(strings[2].lower())
  if src:
   # Only interpret the initializer through INIT_COMPONENT's explicit store.
   # Later AI functions/arithmetic are outside this static component witness.
   dump=read(src.read_bytes());root=dump['prototypes'][dump['root']]
   for index,(op,a,c,b) in enumerate(root['instructions']):
    if op==0x3f and root['kgc'][c|(b<<8)]=='INIT_COMPONENT':
     fragment=json.loads(json.dumps(dump));fragment['prototypes'][fragment['root']]['instructions']=root['instructions'][:index+1]
     try:component=initializer(fragment,{'TRUE':True,'FALSE':False}).get('INIT_COMPONENT',{})
     except (ValueError,KeyError,TypeError,IndexError):pass
     break
   sources[src.name]=hashlib.sha256(src.read_bytes()).hexdigest()
  maximum=component.get('MAX_HP')
  if type(maximum) not in (int,float) or not math.isfinite(maximum) or not 0<maximum<=3.4028234e38:maximum=None
  if maximum is not None:hp=maximum
  npcs[str(identity)]=dict(strings=strings+['',''],script_max_hp=maximum,local_hp=hp)
 def summon_dependencies(identities):
  pending=list(identities);result=set()
  while pending:
   current=pending.pop()
   if current in result:continue
   try:npc(current)
   except (KeyError,ValueError):continue
   result.add(current)
   if current not in npc_dependencies:
    refs=set();src=resource_paths.get(npcs[str(current)]['strings'][2].lower())
    if src:
     refs=summon_targets(read(src.read_bytes()),enums)
    npc_dependencies[current]=refs
   pending.extend(npc_dependencies[current]-result)
  return sorted(result)
 def compile_npc(g,source_index):
  if not isinstance(g,dict):raise ValueError('NPC group shape')
  if 'NPC_ID' not in g:
   options=[]
   for _,child in numbered(g,'SUB_NPC'):
    option=compile_npc(child,source_index);option['weight']=child.get('SUB_NPC_RATE',100)
    if type(option['weight']) is not int or option['weight']<0:raise ValueError('NPC variant rate')
    if option['weight']:options.append(option)
   if not options:raise ValueError('NPC group shape')
   return dict(options=options,source_index=int(source_index))
  identity=resolve(g['NPC_ID'],'NPC_UNIT_ID');npc(identity)
  points=values(g['START_POS'])
  if not points or any(type(p) is not int for p in points):raise ValueError('NPC start points')
  key_code=g.get('KEY_CODE',-1)
  # Current 393AC70 reads a Lua number and truncates to signed i32.
  # Original-reader fixtures: complex-dungeons-20261015/scalar-reader-proof.json.
  if type(key_code) in (int,float) and math.isfinite(key_code) and -2**31<=key_code<2**31:
   key_code=int(key_code)
  e=dict(template=identity,source_index=int(source_index),points=points,active=flag(g,'ACTIVE',True),gage=flag(g,'GAGE_BAR',True),
         ally=flag(g,'ALLY_NPC'),team=g.get('TEAM',1),
         no_drop=flag(g,'NO_DROP'),right=flag(g,'IS_RIGHT'),boss=flag(g,'HAVE_BOSS_GAGE'),boss_lines=g.get('BOSS_GAUGE_HP_LINES',1),
         key_code=key_code,source_key_code=g.get('KEY_CODE',-1),rate=g.get('RATE',100),offset=[g.get('ADD_POS_'+v,0) for v in 'XYZ'])
  if any(type(v) not in (int,float) for v in e['offset']) or type(e['key_code']) is not int:raise ValueError('NPC scalar shape')
  if type(e['team']) is not int or e['team'] not in (0,1,2):raise ValueError('NPC team bound')
  if any(not math.isfinite(v) for v in e['offset']):raise ValueError('Non-finite NPC position')
  if e['boss'] and (type(e['boss_lines']) is not int or not 1<=e['boss_lines']<=65535):raise ValueError('Boss gauge line bound')
  return e
 def compile_part(part,current_stage):
  groups=[]
  for group_index,group in [(-1,part.get('NPC_GROUP',{})),*numbered(part,'NPC_GROUP')]:
   entries=[]
   for source_index,g in sorted(group.items(),key=lambda x:int(x[0])):entries.append(compile_npc(g,source_index))
   groups.append(dict(index=group_index,npcs=entries))
  conditions=[]
  for index,c in numbered(part,'CLEAR_COND'):
   raw_kind=c.get('1')
   if raw_kind is None and name in policy['nil_condition_repair']:raw_kind=policy['nil_condition_repair'][name]
   kind=resolve(raw_kind,'CLEAR_CONDITION')
   if kind not in (0,1,2,3,5,6):raise ValueError('Unsupported clear condition '+str(kind))
   required=values(c.get('NPC_ID',{})) if kind==3 else values(c.get('NPC_KEYCODE',{})) if kind in (1,2) else []
   if kind==3:required=[resolve(v,'NPC_UNIT_ID') for v in required]
   cond=dict(kind=kind,required=required,portal_lines=values(c.get('PORTAL_LINE_INDEX',{})),delay=c.get('DELAY_TIME_CLEAR_SUB_STAGE',0),seconds=c.get('CLEAR_TIME',0),next=[])
   if any(type(cond[k]) not in (int,float) or not 0<=cond[k]<=86400 for k in ('delay','seconds')):raise ValueError('Clear timing bound')
   for _,t in numbered(c,'NEXT_STAGE'):
    mode=resolve(t.get('1'),'CLEAR_TYPE')
    if mode not in (0,1,4):raise ValueError('Unsupported transition '+str(mode))
    stage,part_id,weight=t.get('2'),t.get('3'),t.get('4',100)
    if any(type(v) is not int for v in (stage,part_id,weight)) or not 0<=part_id<128 or weight<0:raise ValueError('Transition shape')
    # CT_STAGE loads a world and starts its first part; CT_SUB_STAGE selects
    # a part within the current world. Redundant source cells are retained
    # as evidence, not interpreted as a cross-world part transition.
    source_target=[stage,part_id]
    if mode==0:stage=current_stage
    elif mode==1:part_id=0
    if weight or identity==policy['add_center']['dungeon']:cond['next'].append(dict(kind=mode,stage=stage,part=part_id,weight=weight,source_target=source_target))
   if not cond['next']:raise ValueError('No clear destination')
   # A condition requiring a script-created actor is not a static kill route.
   variants=[g['npcs'] for g in groups[1:] if g['npcs']] or [[]]
   for variant in variants:
    def identities(entries):
     field='template' if kind==3 else 'key_code';result=set()
     for entry in entries:
      options=entry.get('options',[entry]);result|=set.intersection(*({o[field]} for o in options))
     return result
    present=identities(variant);common=identities(groups[0]['npcs'])
    if required and not set(required)<=present|common:
     if str(identity) in policy['henir']:cond['dynamic_required']=True
     else:raise ValueError('Clear target requires dynamic NPC spawning')
   if kind not in (0,5,6) and not any(g['npcs'] for g in groups):raise ValueError('Empty scripted combat part')
   conditions.append(cond)
  if not conditions:raise ValueError('No supported clear condition')
  return dict(groups=groups,conditions=conditions)
 with data.connect() as db:definitions=[json.loads(r[0]) for r in db.execute('select definition from dungeons order by id')]
 by_file={}
 for definition in definitions:
  identity=definition['dungeonID'];name=definition['dataFileName'];key=name.lower()
  internal=str(identity) in scope['challenge_dependencies']
  if str(identity) not in scope['active'] and not internal:continue
  if key not in by_file:
   try:
    source=resource_paths.get(key)
    if source is None:raise ValueError('Dungeon script absent from local client index')
    # Interpret the pinned original bytecode each build. A stale derived JSON
    # file must not silently change flags or source graph semantics.
    raw=source.read_bytes();parsed=initializer(read(raw),script_globals)
    # Lua numeric table keys become strings in the persisted graph schema.
    tables={'STAGE_LIST':json.loads(json.dumps(parsed['STAGE_LIST']))};stages={}
    source_stages={stage:{i:p for i,p in numbered(body,'SUB_STAGE')} for stage,body in numbered(tables['STAGE_LIST'],'STAGE')}
    if 0 not in source_stages or 0 not in source_stages[0]:raise ValueError('No initial stage/part')
    # Validate every branch reachable from the actual initial part, then prove
    # every reachable vertex has a path to a real CT_GAME destination.
    henir=policy['henir'].get(str(identity));add_center=identity==policy['add_center']['dungeon']
    todo=[(s,p) for s,parts in source_stages.items() for p in parts] if henir else [(0,0)]
    seen=set();edges={};terminal=set()
    while todo:
     point=todo.pop()
     if point in seen:continue
     seen.add(point);s,p=point
     if s not in source_stages or p not in source_stages[s]:raise ValueError('Transition references absent stage/part')
     stages.setdefault(str(s),{'parts':{}})['parts'][str(p)]=compile_part(source_stages[s][p],s)
     edges[point]=set()
     for c in stages[str(s)]['parts'][str(p)]['conditions']:
      for t in c['next']:
       if t['kind']==4:terminal.add(point)
       else:dest=(t['stage'],t['part']);edges[point].add(dest);todo.append(dest)
    reaches=set(terminal)
    while True:
     more={v for v,ds in edges.items() if ds & reaches}-reaches
     if not more:break
     reaches|=more
    if reaches!=seen and not henir and not add_center:raise ValueError('Reachable graph cannot finish')
    visiting=set();done=set()
    def acyclic(point):
     if point in visiting:raise ValueError('Cyclic route requires encounter-specific progression')
     if point in done:return
     visiting.add(point)
     for dest in edges[point]:acyclic(dest)
     visiting.remove(point);done.add(point)
    encounter=None
    if henir:
     pool=[]
     for s,stage in stages.items():
      if set(stage['parts'])!={'0'}:raise ValueError('Henir room has unexpected parts')
      room=stage['parts']['0'];primary=[i for i,c in enumerate(room['conditions']) if not c.get('dynamic_required') and c['kind'] in (0,1,2,3) and any(t['kind']==1 for t in c['next'])]
      if primary and not any(c['kind']==6 for c in room['conditions']):pool.append(dict(stage=int(s),condition=primary[0]))
     if 0 not in [r['stage'] for r in pool] or len(pool)<henir['rounds']:raise ValueError('Insufficient source Henir combat rooms')
     encounter=dict(kind='henir_local_rotation',rounds=henir['rounds'],pool=pool,provenance='local_policy')
    elif add_center:
     encounter=dict(kind='unvisited_stage_pool',**policy['add_center'],provenance='local_policy')
     if set(stages)!={str(v) for v in (encounter['opening'],*encounter['rooms'],encounter['boss'])}:raise ValueError('Add Center source rooms changed')
    elif key=='dungeon_devildom5_goldcastle.lua':
     portals=[]
     for condition in stages['0']['parts']['0']['conditions']:
      if condition['kind']!=3 or len(condition['required'])!=1 or len(condition['next'])!=1:raise ValueError('Gold Castle portal source changed')
      target=condition['next'][0]
      if target['kind']!=1 or target['stage'] not in (1,2,3,4):raise ValueError('Gold Castle destination source changed')
      portals.append(dict(npc=condition['required'][0],stage=target['stage']))
     if {p['stage'] for p in portals}!={1,2,3,4}:raise ValueError('Gold Castle wing source changed')
     encounter=dict(kind='gold_castle',hub=0,wings=[1,2,3],boss=4,portals=portals)
    else:acyclic((0,0))
    source_hash=hashlib.sha256(raw).hexdigest();sources[source.name]=source_hash
    for s,stage in stages.items():
     ready=values(tables['STAGE_LIST']['STAGE'+s].get('READY_NPC',{}))
     identities=set();unresolved=[]
     for value in ready:
      try:identities.add(resolve(value,'NPC_UNIT_ID'))
      except ValueError:unresolved.append(value)
     for room in stage['parts'].values():
      for group in room['groups']:
       for entry in group['npcs']:
        identities.update(o['template'] for o in entry.get('options',[entry]))
     stage['allowed_summons']=summon_dependencies(identities)
     if unresolved:stage['unresolved_preload_entries']=unresolved
    by_file[key]=dict(source=name,source_sha256=source_hash,stages=stages,reachable_parts=len(seen),encounter=encounter)
   except (KeyError,TypeError,ValueError) as exc:by_file[key]=str(exc)
  compiled=by_file[key]
  if isinstance(compiled,str):
   if internal:raise ValueError('Challenge dependency failed: '+str(identity)+': '+compiled)
   issues[str(identity)]=dict(source=name,reason=compiled)
  else:
   destination=internal_routes if internal else routes
   destination[str(identity)]=dict(source=key,min_level=definition.get('m_MinLevel',1),npc_level=definition.get('m_NPCLevel',1))
 graphs={k:v for k,v in by_file.items() if isinstance(v,dict)}
 if '30000' not in routes:raise ValueError('Baseline El Tree route failed; refuse to publish a broken graph pack')
 seed=json.loads((ROOT/'analysis/client-6c6b5180/npc-wire-candidate.json').read_text())['resource_hex']
 attrs=json.loads((ROOT/'analysis/client-6c6b5180/npc-init-candidate.json').read_text())['fields'][2]['hex']
 raid_source=SOURCE/'selection/resources/RaidDungeonData_Common.lua'
 raid=initializer(read(raid_source.read_bytes()),script_globals)
 challenges=[];dependencies=set()
 for call in raid['__symbolic_calls__']:
  if call['function']!='g_pRaidManager.AddRaidChallengeModeInfo':continue
  source=call['arguments'][1]
  if source['m_iChallengeID'] not in (4,5):continue
  nodes=[]
  for entry in values(source['Dungeon']):
   node={field:entry[key] for field,key in [('dungeon','m_iDungeonID'),('count','m_iClearCount'),('flag','m_iClearFlag'),('requires','m_iEnterProgress'),('final','m_bFinalPhase')]}
   if any(type(v) is not int for v in node.values()) or node['dungeon'] not in map(int,internal_routes):raise ValueError('Challenge source node')
   nodes.append(node);dependencies.add(str(node['dungeon']))
  challenges.append(dict(challenge=source['m_iChallengeID'],phase=source['m_iPhaseID'],seconds=source['m_iLimitTimeSec'],dummy=source['m_iPhaseDummyDungeonID'],nodes=nodes))
 if dependencies!=set(internal_routes):raise ValueError('Challenge scope/source disagreement')
 sources[raid_source.name]=hashlib.sha256(raid_source.read_bytes()).hexdigest()
 payload=dict(routes=routes,internal_routes=internal_routes,challenges=challenges,graphs=graphs,npcs=npcs,spawn_seed=seed,attribute_seed=attrs)
 raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf8')
 destination=ROOT/'els_server/data/client';(destination/'dungeon_routes.json').write_bytes(raw)
 manifest=dict(schema_version=1,client_sha256=CLIENT_SHA,payload_sha256=hashlib.sha256(raw).hexdigest(),count=len(routes),
               graphs=len(graphs),internal_routes=len(internal_routes),source_sha256=sources,unsupported=issues,scope='Captured solo graphs and internal challenge nodes; local combat/rewards; scripted encounter admission requires progression.')
 manifest['selection_scope_sha256']=hashlib.sha256(scope_raw).hexdigest()
 manifest['local_policy_sha256']=hashlib.sha256(policy_raw).hexdigest()
 manifest['current_selectable_count']=len(scope['active'])
 (destination/'dungeon_routes.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
 (SOURCE/'route-audit.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(dict(routes=len(routes),graphs=len(graphs),reasons=collections.Counter(v['reason'] for v in issues.values()),bytes=len(raw)),ensure_ascii=False))
if __name__=='__main__':build()
