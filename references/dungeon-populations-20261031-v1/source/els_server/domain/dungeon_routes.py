"""Pinned static solo dungeon graphs and per-run local population.
Source transitions/identities are native; combat and branch selection are local.
"""
import functools,hashlib,json,math,struct,time,uuid
from els_server.game_data import CLIENT_SHA,DATA_DIR
from els_server.domain.dungeon_npcs import resource_dto,encode_npc
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event

SOURCE_NPC_LEVEL_OVERRIDES={('cfa5b87ea61cc343f5347f497a1cb303f18be6df6a1bdd11e3bff74547deba67', 0, 0, 1, 9011): 40, ('5573ca1db761bda7de68f7fb420d1a80f386d0ed0dcbd80fce2719ca57611aff', 0, 0, 1, 9020): 99, ('3f5e999f1e8c4dc3c63525d7dfc231ec8b40abcadeacb2e4d2ae82cb2c7fe2e0', 0, 0, 1, 9010): 99}

# Original NPC_GROUP_RATE values, keyed by Lua source SHA and room.
SOURCE_NPC_GROUP_WEIGHTS={
 ('2ad86a70dc61c61d3df3dbeaccf3d09fb2253b99a7db57242eb214a514bbe365', 0, 0): (33, 33, 34),
 ('2ad86a70dc61c61d3df3dbeaccf3d09fb2253b99a7db57242eb214a514bbe365', 1, 0): (33, 33, 34),
 ('2ad86a70dc61c61d3df3dbeaccf3d09fb2253b99a7db57242eb214a514bbe365', 1, 1): (33, 33, 34),
 ('2ad86a70dc61c61d3df3dbeaccf3d09fb2253b99a7db57242eb214a514bbe365', 1, 2): (33, 33, 34),
 ('2ad86a70dc61c61d3df3dbeaccf3d09fb2253b99a7db57242eb214a514bbe365', 2, 0): (33, 33, 34),
 ('2ad86a70dc61c61d3df3dbeaccf3d09fb2253b99a7db57242eb214a514bbe365', 2, 1): (33, 33, 34),
 ('2ad86a70dc61c61d3df3dbeaccf3d09fb2253b99a7db57242eb214a514bbe365', 3, 0): (25, 25, 25, 25),
 ('4f2e699405bc182f1892bfb2868fca428668290bd2178d87d072446adaab8a3b', 0, 0): (100,),
 ('4f2e699405bc182f1892bfb2868fca428668290bd2178d87d072446adaab8a3b', 1, 0): (100,),
 ('4f2e699405bc182f1892bfb2868fca428668290bd2178d87d072446adaab8a3b', 2, 0): (100,),
 ('4f2e699405bc182f1892bfb2868fca428668290bd2178d87d072446adaab8a3b', 3, 0): (100,),
 ('9059e50b72703832ee50d6ad9f9955703cfb6486c9e4b98421a771aece9d057a', 0, 0): (33, 33, 34),
 ('9059e50b72703832ee50d6ad9f9955703cfb6486c9e4b98421a771aece9d057a', 0, 1): (33, 33, 34),
 ('9059e50b72703832ee50d6ad9f9955703cfb6486c9e4b98421a771aece9d057a', 1, 0): (33, 33, 34),
 ('9059e50b72703832ee50d6ad9f9955703cfb6486c9e4b98421a771aece9d057a', 2, 0): (33, 33, 34),
 ('9059e50b72703832ee50d6ad9f9955703cfb6486c9e4b98421a771aece9d057a', 2, 1): (33, 33, 34),
 ('9059e50b72703832ee50d6ad9f9955703cfb6486c9e4b98421a771aece9d057a', 2, 2): (33, 33, 34),
 ('9059e50b72703832ee50d6ad9f9955703cfb6486c9e4b98421a771aece9d057a', 3, 0): (33, 33, 34),
 ('b2fc7a644eb702d4840af7c0ad7ba9fa7926e3182d6e1ef0335193228ad807c2', 1, 0): (50, 50),
 ('c5c13300ddb677fa274194036820b79be46c5f19b1c406e17f01497175344fa2', 0, 0): (33, 33, 34),
 ('c5c13300ddb677fa274194036820b79be46c5f19b1c406e17f01497175344fa2', 0, 1): (33, 33, 34),
 ('c5c13300ddb677fa274194036820b79be46c5f19b1c406e17f01497175344fa2', 1, 0): (33, 33, 34),
 ('c5c13300ddb677fa274194036820b79be46c5f19b1c406e17f01497175344fa2', 1, 2): (50, 50),
 ('c5c13300ddb677fa274194036820b79be46c5f19b1c406e17f01497175344fa2', 2, 0): (33, 33, 34),
 ('c5c13300ddb677fa274194036820b79be46c5f19b1c406e17f01497175344fa2', 3, 0): (33, 33, 34),
 ('e13df7034c4af2db9bb49ea28348f1651f8a7c3918730e29c5d36321f8571bbb', 0, 0): (100,),
 ('e5c9b9d1e6553e2e30a112a0fc06515ec73d02f0fc5bb8d5aa534efde650d214', 0, 0): (50, 50),
 ('f8fcbe09cad35b426a3221cff7173febb0acb457eea3ab57296c53d391df248e', 0, 0): (33, 33, 34),
 ('f8fcbe09cad35b426a3221cff7173febb0acb457eea3ab57296c53d391df248e', 0, 1): (33, 33, 34),
 ('f8fcbe09cad35b426a3221cff7173febb0acb457eea3ab57296c53d391df248e', 1, 0): (33, 33, 34),
 ('f8fcbe09cad35b426a3221cff7173febb0acb457eea3ab57296c53d391df248e', 1, 1): (33, 33, 34),
 ('f8fcbe09cad35b426a3221cff7173febb0acb457eea3ab57296c53d391df248e', 1, 2): (33, 33, 34),
 ('f8fcbe09cad35b426a3221cff7173febb0acb457eea3ab57296c53d391df248e', 2, 0): (33, 33, 34),
 ('f8fcbe09cad35b426a3221cff7173febb0acb457eea3ab57296c53d391df248e', 2, 1): (33, 33, 34),
 ('f8fcbe09cad35b426a3221cff7173febb0acb457eea3ab57296c53d391df248e', 2, 2): (33, 33, 34),
}

class RouteCatalog:
 def __init__(self,directory=DATA_DIR):
  raw=(directory/'dungeon_routes.json').read_bytes();m=json.loads((directory/'dungeon_routes.manifest.json').read_text(encoding='utf8'))
  if m['schema_version']!=1 or m['client_sha256']!=CLIENT_SHA or hashlib.sha256(raw).hexdigest()!=m['payload_sha256']:raise ValueError('Dungeon graph identity/checksum')
  from els_server.paths import PROJECT_ROOT
  scope_raw=(PROJECT_ROOT/'config/dungeon_scope.json').read_bytes()
  if hashlib.sha256(scope_raw).hexdigest()!=m['selection_scope_sha256']:raise ValueError('Dungeon selection scope changed; rebuild routes')
  if hashlib.sha256((PROJECT_ROOT/'config/dungeon_local_rules.json').read_bytes()).hexdigest()!=m['local_policy_sha256']:raise ValueError('Dungeon encounter policy changed; rebuild routes')
  self._data=json.loads(raw);self.manifest=m
  scope=json.loads(scope_raw);self.entry_aliases={}
  # Current manual icons still submit the family's base ID at difficulty 0.
  # Only explicitly superseded members of a current layout family resolve
  # to its admitted route; removed and unused families never gain admission.
  for key,row in scope['active'].items():
   for evidence in row.get('evidence',[]):
    if evidence.get('kind')!='current_layout_difficulty_family':continue
    for alias in evidence['group']:
     if scope['excluded'].get(str(alias),{}).get('reason')!='superseded_ordinary_difficulty':continue
     if alias in self.entry_aliases and self.entry_aliases[alias]!=int(key):raise ValueError('Ambiguous current dungeon family')
     self.entry_aliases[alias]=int(key)
  if len(self._data['routes'])!=m['count'] or len(self._data['graphs'])!=m['graphs']:raise ValueError('Dungeon graph count')
  if len(self._data['internal_routes'])!=m['internal_routes']:raise ValueError('Challenge dependency count')
  events=self._data.get('event_routes',{})
  if len(events)!=m.get('event_routes',0) or set(events)!=set(scope.get('event_entries',{})):raise ValueError('Event route scope/count')
  from els_server.domain.event_dungeons import definition as event_definition
  for key,row in events.items():
   expected=event_definition(int(key));graph=self._data['graphs'][row['source']]
   if graph['source_sha256']!=expected['source_sha256']:raise ValueError('Event route source identity')
 def supports(self,identity,*,internal=False):return type(identity) is int and (str(identity) in self._data['routes'] or str(identity) in self._data.get('event_routes',{}) or internal and str(identity) in self._data.get('internal_routes',{}))
 def entry_identity(self,identity):return self.entry_aliases.get(identity,identity) if type(identity) is int else identity
 def static_npc_level(self,identity,graph,stage,part,source):
  # Only current fixed-level source routes. Relative-player-level120010
  # retains its previous behavior until its original roster rule is closed.
  if identity in (38300,120010) or str(identity) in self._data.get('event_routes',{}):return None
  route=self._data['routes'].get(str(identity),self._data['internal_routes'].get(str(identity)))
  if route is None or self._data['graphs'][route['source']]['source_sha256']!=graph['source_sha256']:
   raise ValueError('NPC level original route identity')
  overrides=SOURCE_NPC_LEVEL_OVERRIDES
  level=overrides.get((graph['source_sha256'],stage,part,source['source_index'],source['template']),route['npc_level'])
  if type(level)is not int or not 1<=level<=127:raise ValueError('NPC source level byte bound')
  return level
 def graph(self,identity,*,internal=False):
  if not self.supports(identity,internal=internal):raise ValueError('Dungeon does not have an admitted solo route')
  route=next(rows[str(identity)] for rows in (self._data['routes'],self._data.get('event_routes',{}),self._data['internal_routes']) if str(identity) in rows)
  return json.loads(json.dumps(self._data['graphs'][route['source']]))

@functools.lru_cache(maxsize=1)
def route_catalog():return RouteCatalog()

def npc_initialization(catalog,template,hp,*,source_context=None,dynamic_context=None,field_context=None):
 native=catalog._data['npcs'][str(template)]
 attrs=bytearray.fromhex(catalog._data['attribute_seed']);struct.pack_into('<f',attrs,4,hp);struct.pack_into('<ff',attrs,8,20,20)
 from els_server.domain.raid_npc_stats import apply
 apply(catalog,template,attrs,source_context)
 from els_server.domain.boss_npc_stats import apply as apply_boss
 apply_boss(catalog,template,attrs,source_context,dynamic_context=dynamic_context,field_context=field_context)
 strings=native['strings'];init=struct.pack('>iB',template,0)+b''.join(wstring(s) for s in strings[:4])+b'\1'+b''.join(wstring(s) for s in strings[4:])
 return init+b''.join(attrs[o:o+4][::-1] for o in range(0,0x60,4))+bytes(2)

class DungeonRun:
 def __init__(self,identity,run_id,*,clock=time.monotonic,internal=False,hp_context=None):
  self.catalog=route_catalog();self.graph=self.catalog.graph(identity,internal=internal);self.identity=identity
  self.run_id=str(uuid.UUID(run_id));self.clock=clock;self.stage=0;self.part=0
  self.hp_context=hp_context
  if hp_context is not None:hp_context.bind_run(self)
  self.encounter=self.graph.get('encounter');self.completed_stages=set();self.visits=0
  self.round=0;self.rotation=[]
  self.dynamic_requests={}
  self.completed_transition=None
  if self.encounter and self.encounter['kind']=='henir_local_rotation':
   pool=[r['stage'] for r in self.encounter['pool'] if r['stage']!=0]
   pool.sort(key=lambda stage:self.draw('henir-room:'+str(stage),2**128))
   self.rotation=[0,*pool[:self.encounter['rounds']-1]]
  self.defeated={};self.parts={};self.stage_wires={};self.next=None;self.ready_at=None;self.started_at=None;self.portal_requested=False
  self._load_stage(0)
  from els_server.domain.legacy_pve_exp import bind_run
  bind_run(self)
  from els_server.domain.formal_raid_economy import definition as raid_economy_definition
  if raid_economy_definition(identity) is not None:
   from els_server.domain.gm_rates import snapshot as raid_rate_snapshot
   self.formal_raid_experience_bp=raid_rate_snapshot()['experience_bp']
 def draw(self,label,total):
  return int.from_bytes(hashlib.sha256((self.run_id+':'+label).encode()).digest(),'big')%total
 def _load_stage(self,stage):
  data=self.catalog._data;key=0;parts={};spawn_parts=[];initial=[];hero_keys=[]
  suppressed=set()
  if self.encounter and self.encounter['kind']=='gold_castle' and stage==self.encounter['hub']:
   suppressed={p['npc'] for p in self.encounter['portals'] if p['stage'] in self.completed_stages}
  for part_id,part in sorted(self.graph['stages'][str(stage)]['parts'].items(),key=lambda kv:int(kv[0])):
   base=part['groups'][0]['npcs'];alternatives=part['groups'][1:]
   chosen_group=None
   if alternatives:
    weights=SOURCE_NPC_GROUP_WEIGHTS[self.graph['source_sha256'],stage,int(part_id)]
    draw=self.draw(f'group:{stage}:{part_id}',sum(weights))
    for group,weight in zip(alternatives,weights):
     draw-=weight
     if draw<0:chosen_group=group;break
   chosen=chosen_group['npcs'] if chosen_group else []
   entries=[]
   for index,source in enumerate([*base,*chosen]):
    if 'options' in source:
     draw=self.draw(f'variant:{stage}:{part_id}:{index}',sum(o['weight'] for o in source['options']))
     for option in source['options']:
      draw-=option['weight']
      if draw<0:source=option;break
    # Presence is selected once per run/source actor. Clear checks below use
    # the emitted roster, so an omitted optional actor cannot block a room.
    if source['rate']<100 and self.draw(f'presence:{stage}:{part_id}:{index}',100)>=source['rate']:
     key+=1;continue
    # A fixed run seed picks one of the original alternative spawn positions.
    template=source['template'];native=data['npcs'][str(template)]
    if template in suppressed:key+=1;continue
    from els_server.domain.formal_npc_hp import maximum,level as formal_level
    npc_level=self.catalog.static_npc_level(self.identity,self.graph,stage,int(part_id),source)
    if npc_level is None:npc_level=formal_level(self.catalog,self.identity)
    context=(self.identity,self.graph['source_sha256'],npc_level,stage,int(part_id),-1 if index<len(base) else chosen_group['index'],source['source_index'])
    hp=maximum(self.catalog,template,dungeon=self.identity,npc_level=npc_level,boss=source['boss'],source_context=context)
    if self.hp_context is not None:
     hp=self.hp_context.source_hp(self,stage,int(part_id),-1 if index<len(base) else chosen_group['index'],source,hp)
    point=source['points'][self.draw(f'point:{stage}:{part_id}:{index}',len(source['points']))]
    raw=bytearray.fromhex(data['spawn_seed']);struct.pack_into('<iii',raw,0,key,template,source['key_code'])
    struct.pack_into('<i',raw,0x28,point);struct.pack_into('<3f',raw,0x30,*source['offset'])
    raw[0x2c]=int(source['active']);raw[0x2d]=int(source['gage']);raw[0x48]=int(source['right'])
    level=self.catalog.static_npc_level(self.identity,self.graph,stage,int(part_id),source)
    raw[0xc]=npc_level
    # 107F480 passes resource +3C (team) and +50 (ally) to 8A9C40;
    # the original source's team default remains 1 unless TEAM is explicit.
    raw[0x3c]=source.get('team',1);raw[0x50]=int(source.get('ally',False))
    if source['boss']:
     if type(source['boss_lines']) is not int or not 1<=source['boss_lines']<=65535:raise ValueError('Boss gauge line bound')
     raw[0x44]=1;struct.pack_into('<H',raw,0x58,source['boss_lines'])
    init=npc_initialization(self.catalog,template,hp,source_context=context)
    from els_server.domain.native_hero_inputs import source_maximum
    hp,hero_native=source_maximum(self.catalog,template,hp,context)
    if hero_native:hero_keys.append(key)
    wire=encode_npc(resource_dto(raw),0)
    entries.append({**source,'key':key,'hp':hp,'start_point':point,'wire':wire,'init':init})
    initial.append(struct.pack('>i',key)+init);key+=1
   parts[int(part_id)]={**part,'npcs':entries}
   spawn_parts.append(struct.pack('>iII',int(part_id),0,len(entries))+b''.join(n['wire'] for n in entries))
  if key>16384:raise ValueError('Dungeon NPC count bound')
  spawns=struct.pack('>I',len(spawn_parts))+b''.join(spawn_parts)
  from els_server.domain.native_hero_inputs import ability_metadata
  metadata=ability_metadata(hero_keys)
  payload=struct.pack('>ii',stage,0)+spawns+metadata+struct.pack('>I',len(initial))+b''.join(initial)+bytes(8)
  self.stage_wires[stage]=Event(0x201,kind=0xb2,payload=payload);self.parts=parts
  self.defeated={};self.stage=stage
  self.visits+=1
 @property
 def current(self):return self.parts[self.part]
 @property
 def reserved_keys(self):return {n['key'] for p in self.parts.values() for n in p['npcs']}
 def new_npc_keys(self,count,other_keys):
  # 1AA4A40 searches actor+3D0, independently of 855070's 80 physical
  # slots. Never recycle a network identity while old death replies exist.
  first=max(self.reserved_keys|set(other_keys),default=-1)+1
  if not 1<=count<=64 or first+count>16384:raise ValueError('NPC instance identity bound')
  return list(range(first,first+count))
 def loaded(self):
  if self.started_at is None:self.started_at=self.clock()
 def population_event(self):
  if self.hp_context is not None:self.hp_context.check(self,emitting=True)
  return self.stage_wires[self.stage]
 def condition_ready(self,c):
  if self.encounter and self.encounter['kind']=='henir_local_rotation':
   expected=next(r['condition'] for r in self.encounter['pool'] if r['stage']==self.stage)
   if c is not self.current['conditions'][expected]:return False
  if self.encounter and self.encounter['kind']=='gold_castle' and self.stage==self.encounter['hub']:
   destination=c['next'][0]['stage']
   if destination in self.completed_stages:return False
   if destination==self.encounter['boss'] and not set(self.encounter['wings'])<=self.completed_stages:return False
  npcs=self.current['npcs'];dead=set(self.defeated);kind=c['kind']
  if kind in (0,5):return (kind==0 or self.portal_requested) and all(n['key'] in dead for n in npcs if n['active'] and n.get('team',1)!=0)
  if kind in (1,2):
   keys=[n['key'] for n in npcs if n['key_code'] in c['required']]
   # Only the two source-pinned 30282 script exits; raid controllers keep
   # their original retirement requirement even when all hostiles are dead.
   if (kind==1 and self.identity==30282 and (self.stage,self.part) in ((0,1),(1,1))
       and c['required']==[1]
       and self.graph['source_sha256']=='3da2896f31f56f9f1c1239455bd40dbab24c87b46b63409ca6e47a54f956ca5d'
       and self.graph==self.catalog.graph(self.identity)):
    gates=[n for n in npcs if n['key_code']==1]
    live=[n for n in npcs if n['active'] and n.get('team',1)!=0]
    if (gates and all(n['template']==156 and not n['active'] and n.get('no_drop')
                     and not n.get('ally') and n.get('team',1)==1 for n in gates)
        and live and all(n['key'] in dead for n in live)):
     return True
   return bool(keys) and (any(k in dead for k in keys) if kind==2 else all(k in dead for k in keys))
  if kind==3:
   # Only the two native dragon-nest doors; class103 controllers elsewhere
   # still require their exact original retirement, even in an empty room.
   if (self.identity==30182 and (self.stage,self.part) in ((0,1),(1,1))
       and c['required']==[145]
       and self.graph['source_sha256']=='beb270845a77bef951e89efe21f3910a2d72b0fade4de3ffe8fe2f054de1a295'
       and self.graph==self.catalog.graph(self.identity)):
    gates=[n for n in npcs if n['template']==145]
    live=[n for n in npcs if n['active'] and n.get('team',1)!=0]
    if (gates and all(not n['active'] and n.get('no_drop') and not n.get('ally')
                     and n.get('team',1)==1 for n in gates)
        and live and all(n['key'] in dead for n in live)):return True
   required=[n['key'] for n in npcs if n['template'] in c['required']]
   return bool(required) and all(k in dead for k in required)
  if kind==6:return self.started_at is not None and self.clock()-self.started_at>=c['seconds']
  return False
 def poll_ready(self):
  if self.started_at is None:return False
  if self.next is None:
   for c in self.current['conditions']:
    if not self.condition_ready(c):continue
    targets=c['next']
    if self.encounter and self.encounter['kind']=='henir_local_rotation':
     targets=[dict(kind=4 if self.round+1==len(self.rotation) else 1,stage=self.stage if self.round+1==len(self.rotation) else self.rotation[self.round+1],part=0,weight=100)]
    elif self.encounter and self.encounter['kind']=='unvisited_stage_pool' and self.stage!=self.encounter['boss']:
     cleared=self.completed_stages|{self.stage};targets=[t for t in targets if t['weight']>0 and t['stage'] not in cleared and t['stage']!=self.encounter['boss']]
     if not targets:
      if not set(self.encounter['rooms'])<=cleared:raise ValueError('No unvisited encounter destination')
      targets=[dict(kind=1,stage=self.encounter['boss'],part=0,weight=100)]
    total=sum(t['weight'] for t in targets);draw=self.draw(f'exit:{self.stage}:{self.part}:{self.round}',total)
    for t in targets:
     draw-=t['weight']
     if draw<0:self.next=t;break
    self.ready_at=self.clock()+c['delay'];break
  return self.next is not None and self.clock()>=self.ready_at
 def advance(self):
  if not self.poll_ready():raise ValueError('Part has not satisfied its source clear condition')
  target=dict(self.next)
  if target['kind']==4:return 'clear'
  if target['kind']==0:
   if target['stage']!=self.stage:raise ValueError('Sub-part crosses world stage')
   self.part=target['part'];transition='part'
  else:
   self.completed_stages.add(self.stage)
   self.round+=1
   self._load_stage(target['stage']);self.part=target['part'];transition='stage'
  self.next=None;self.ready_at=None;self.started_at=None;self.portal_requested=False
  return transition
