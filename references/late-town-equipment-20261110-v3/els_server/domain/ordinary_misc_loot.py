"""Source-bound ordinary misc drops; all new numeric choices are local rules."""
import functools,hashlib,json,secrets,sqlite3,struct,uuid
from pathlib import Path
from els_server.storage.read_scope import canonical_path
from contextlib import closing

POLICY='ordinary-misc-ground-local-20261104-v1'
ATMA_TEMPLE=35710

@functools.lru_cache(maxsize=1)
def catalog():
 directory=Path(__file__).resolve().parents[1]/'data'
 raw=(directory/'ordinary_misc_loot.json').read_bytes();manifest=json.loads((directory/'ordinary_misc_loot.manifest.json').read_bytes());p=json.loads(raw)
 from els_server.game_data import client_data,CLIENT_SHA
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
 d=client_data()
 if(manifest['client_sha256']!=CLIENT_SHA or hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']or p['policy']!=POLICY or p['client_sha256']!=CLIENT_SHA or p['catalog_sha256']!=d.manifest['catalog_sha256']):raise ValueError('Ordinary misc source identity')
 for key,row in p['items'].items():
  t=int(key);n=d.item(t)
  if(hashlib.sha256(n['record']).hexdigest()!=row['record_sha256']or n['item_type']!=row['item_type']or(VERIFIED_TEMPLATES.get(t),TEMPLATE_BAG_GROUPS.get(t),TEMPLATE_MAX_STACKS.get(t))!=(row['metadata'],row['group'],row['max_stack'])):raise ValueError('Ordinary misc registered factory')
 return p

def _context(s,npc):
 run=s.dungeon_run
 if run is None:
  from els_server.domain.pve_economy_flow import _identity
  old=_identity(s,npc)
  return {k:old[k]for k in ('owner','run_id','dungeon','stage','part','visits','npc_key','graph_sha256')},old['source_index']
 return dict(owner=s.account.uid,run_id=s.reward_run_id,dungeon=run.identity,stage=run.stage,part=run.part,visits=run.visits,npc_key=npc['key'],graph_sha256=run.graph['source_sha256']),npc['source_index']

def _state(s,npc):
 run=s.dungeon_run
 return(s.account,s.account.store,s.account.uid,s.account.account_id,s.shop_session_id,s.reward_run_id,s.phase,s.client_build,
  run,run.stage if run is not None else s.gate_stage,run.part if run is not None else 0,run.visits if run is not None else s.gate_stage+1,
  (run.run_id,run.graph['source_sha256'])if run is not None else None,
  tuple(npc.get(k)for k in ('key','template','source_index','active','boss','no_drop','team','ally','dynamic')))

def reward_actor(run,npc):
 row=catalog()['maps'].get(str(run.identity),{}).get('reward_actor')if run is not None else None
 if row is None or(npc['template'],npc.get('source_index'))!=(row['source']['template'],row['source']['source_index']):return None
 from els_server.domain.scene_actor_retirements import source_rule
 if source_rule(run,npc)is None:raise ValueError('Giant reward actor original source')
 predecessors=[n for n in run.current['npcs']if(n['template'],n.get('source_index'))==(row['predecessor']['template'],row['predecessor']['source_index'])]
 if len(predecessors)!=1 or any(predecessors[0].get(k)!=v for k,v in row['predecessor'].items()):raise ValueError('Giant reward actor predecessor source')
 proof=run.defeated.get(predecessors[0]['key'])
 if not isinstance(proof,bytes)or not proof:raise ValueError('Giant reward actor predecessor alive')
 return dict(template=npc['template'],source_index=npc['source_index'],predecessor_template=predecessors[0]['template'],proof_sha256=hashlib.sha256(proof).hexdigest())

class _Source:
 def __init__(self,s,npc):
  self.s=s;self.npc=npc;self.bound=_state(s,npc);self.c,index=_context(s,npc)
  self.path=canonical_path(s.account.store.path);self.account=s.account.account_id
  row=catalog()['maps'][str(self.c['dungeon'])]
  from els_server.domain.dungeon_routes import route_catalog
  graph=route_catalog()._graph(self.c['dungeon'])
  if row['graph_sha256']!=self.c['graph_sha256']or row['graph_sha256']!=graph['source_sha256']:raise ValueError('Ordinary misc original graph')
  def leaves(n):
   for value in n.get('options',[n]):yield value
  entries=graph['stages'][str(self.c['stage'])]['parts'][str(self.c['part'])]['groups']
  matching=[n for group in entries for node in group['npcs']for n in leaves(node)if(n['template'],n['source_index'])==(npc['template'],index)and n['active']and not n['no_drop']and not n.get('ally')and n.get('team',1)!=0]
  if not matching:raise ValueError('Ordinary misc exact hostile static actor')
  self.origin=dict(policy=POLICY,source_template=npc['template'],source_index=index,boss=bool(matching[0]['boss']),graph_sha256=graph['source_sha256'])
  actor=reward_actor(s.dungeon_run,npc)
  if actor is not None:self.origin['reward_actor']=actor
  from els_server.game_data import client_data
  self.family=client_data().unit(s.account.character_identity()['unit_class'])['unitType']
 def validate(self,db):
  from els_server.domain.dungeon_hp_c1 import _lease
  from els_server.storage.item_actor import require_active_character
  from els_server.storage.profession_state import require_owner
  s=self.s;run=s.dungeon_run
  if(_state(s,self.npc)!=self.bound or not _lease(s)or s.phase!='dungeon_active'or not s.item_test or not s.reward_test or not s.drop_probe or getattr(s,'released',False) or self.npc['key']in s.defeated_npcs):raise ValueError('Ordinary misc source changed before commit')
  if run is not None and not any(n is self.npc for n in run.current['npcs']):raise ValueError('Ordinary misc loaded actor changed')
  if self.origin.get('reward_actor')!=reward_actor(run,self.npc):raise ValueError('Giant reward actor predecessor changed')
  attached=db.execute('PRAGMA database_list').fetchall()
  if(not db.in_transaction or any(r[1]not in('main','temp')for r in attached)or canonical_path(next(r[2]for r in attached if r[1]=='main'))!=self.path):raise ValueError('Ordinary misc original writer')
  require_active_character(db,s.account.uid);require_owner(db,s.account.uid,self.account)
  return True
 def issue(self,db,c,proof,start_id,xyz,randbelow):
  if any(c.get(k)!=v for k,v in self.c.items()):raise ValueError('Ordinary misc original issue identity')
  from els_server.storage.ordinary_misc_loot import issue
  return issue(db,self,proof,start_id,xyz,randbelow)

def source(s,npc):
 mid=s.dungeon_run.identity if s.dungeon_run is not None else s.dungeon_id
 if(str(mid)not in catalog()['maps']or s.phase!='dungeon_active'or not s.item_test or not s.reward_test or not s.drop_probe or npc.get('dynamic')or not npc.get('active')or npc.get('no_drop')or npc.get('ally')or npc.get('team',1)==0):return None
 from els_server.domain.dungeon_hp_c1 import _lease
 if not _lease(s):return None
 return _Source(s,npc)

def plans(source,randbelow,drop_bp):
 from els_server.domain.elixir_economy import hit
 from els_server.domain.dungeon_equipment_loot_rules import integer_draw
 p=catalog();m=p['maps'][str(source.c['dungeon'])];boss=source.origin['boss']or source.origin.get('reward_actor')is not None;result=[]
 for rule in p['common']+m['extra_materials']:
  if rule.get('weekly_temple_reward'):continue
  if 'stage'in rule and source.c['stage']!=rule['stage']:continue
  if hit(rule['boss_bp'if boss else'ordinary_bp'],10000,randbelow,drop_bp):result.append((rule['template'],rule['quantity']))
 if m['ingredients']and hit(p['cooking']['boss_bp'if boss else'ordinary_bp'],10000,randbelow,drop_bp):
  result.append((m['ingredients'][integer_draw(len(m['ingredients']),randbelow)],1))
 if m['regional_ingredients']and hit(p['regional_cooking']['boss_bp'if boss else'ordinary_bp'],10000,randbelow,drop_bp):
  result.append((m['regional_ingredients'][integer_draw(len(m['regional_ingredients']),randbelow)],1))
 pool=[t for t in m['equipment']if m['wear_family'][str(t)]in(0,source.family)]
 if source.c['dungeon']!=ATMA_TEMPLE and boss and ('equipment_stage'not in m or source.c['stage']==m['equipment_stage']) and pool and hit(p['equipment']['boss_bp'],10000,randbelow,drop_bp):result.append((pool[integer_draw(len(pool),randbelow)],1))
 return result

def temple_rewards(source,randbelow):
 from els_server.domain.dungeon_equipment_loot_rules import integer_draw
 row=catalog()['maps'][str(ATMA_TEMPLE)]
 fragments=[(r['template'],r['quantity']) for r in row['extra_materials']
            if r.get('weekly_temple_reward') and r['stage']==source.c['stage']]
 # Preserve the installed finite equipment selector for this map.
 pool=row['equipment']
 return [(pool[integer_draw(len(pool),randbelow)],1),*fragments]

def quantity(identity,template):
 p=catalog();m=p['maps'][str(identity)]
 for r in p['common']+m['extra_materials']:
  if r['template']==template:return r['quantity']
 if template in m['ingredients']+m['regional_ingredients']+m['equipment']:return 1
 raise ValueError('Ordinary misc template outside map')

def append_to_shadow(db,source,shadow,proof,xyz,*,randbelow=secrets.randbelow):
 from els_server.domain.dungeon_drops import ground_drop_notice
 # The shared storage issue validates this same source before its first SQL
 # mutation. The caller validates it again after all native preencoding.
 rows=source.issue(db,source.c,proof,shadow.world_drop_sequence,xyz,randbelow);events=[]
 for row in rows:
  key=row['drop_id']
  if key in shadow.world_drops:raise ValueError('Ordinary misc ground identity collision')
  event=ground_drop_notice(key,row['xyz'],uid=source.c['owner'],template=row['template']);row['payload_hex']=event.payload.hex()
  shadow.world_drops[key]=dict(row);shadow.world_drop_sequence=key+1;shadow.world_drop_issued=dict(row);events.append(event)
 if source.c['dungeon']==ATMA_TEMPLE and source.origin.get('reward_actor') is not None:
  from els_server.protocol.weekly_dungeon_counts import notification
  events.append(notification(db,source.c['owner']))
 return events

def _claim_binding(s,drop):
 from els_server.domain.dungeon_hp_c1 import _lease
 run=s.dungeon_run;mid=run.identity if run is not None else s.dungeon_id
 if(not _lease(s)or s.phase!='dungeon_active'or not s.item_test or not s.drop_probe or s.world_drops.get(drop['drop_id'])is not drop
    or drop['source']!=POLICY or drop['owner']!=s.account.uid or drop['run_id']!=s.reward_run_id or drop['dungeon']!=mid):raise ValueError('Ordinary misc pickup lease')
 c={k:drop[k]for k in ('owner','run_id','dungeon','stage','part','visits','npc_key','graph_sha256')}
 if c['graph_sha256']!=catalog()['maps'][str(mid)]['graph_sha256']:raise ValueError('Ordinary misc pickup graph')
 return(s.account,s.account.store,s.shop_session_id,s.reward_run_id,s.account.account_id,canonical_path(s.account.store.path),c)

def claim(s,request,drop):
 from els_server.protocol.protocol_codec import Event,encode_event
 from els_server.domain.dungeon_drops import ground_pickup_notice,pickup_inventory_notice
 from els_server.storage.inventory_state import InventoryFull
 try:bound=_claim_binding(s,drop)
 except(ValueError,KeyError):return[]
 def validate(db):
  from els_server.storage.item_actor import require_active_character
  from els_server.storage.profession_state import require_owner
  if _claim_binding(s,drop)!=bound:raise ValueError('Ordinary misc pickup changed')
  require_active_character(db,s.account.uid);require_owner(db,s.account.uid,s.account.account_id)
  return True
 def prepare(items,replayed):
  replies=[Event(0x201,kind=0xd1,payload=bytes(4))]
  if not replayed:replies.append(ground_pickup_notice(drop['drop_id'],s.account.uid,template=drop['template']))
  replies.append(pickup_inventory_notice(items))
  for event in replies:encode_event(event)
  return replies
 from els_server.storage.ordinary_misc_loot import claim as commit
 try:result=commit(bound[5],bound[6],drop,request,s.account.account_id,prepare,validate)
 except InventoryFull:return[Event(0x201,kind=0xd1,payload=struct.pack('>i',-1))]
 except ValueError:return[]
 drop['pickup_committed']=True;s.pickup_receipt=dict(dungeon_run_id=s.reward_run_id,drop_id=drop['drop_id'],replayed=result['replayed'])
 return result['reply']
