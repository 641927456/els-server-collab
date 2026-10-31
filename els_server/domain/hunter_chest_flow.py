"""Generated optional actors bound to original run/part/visit/roster and SQL.

No damage simulation, class101 wildcard, new source on death, client timer or
special old-item producer. Existing native combat, ground and pickup paths run.
"""
import copy,hashlib,math,secrets,sqlite3,struct,time,uuid
from pathlib import Path
from els_server.domain.hunter_chest_rules import SOURCE_ROUTES,POLICY,grade,digest
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol import hunter_chest_messages as wire
from els_server.storage import hunter_chest as storage

def _checked(s,dispatcher=None,room=None):
 from els_server.domain.dungeon_equipment_loot_flow import current_lease
 from els_server.domain.manufacture_flow import _saved_paths,_binding
 run=s.dungeon_run
 if run is None or run.identity not in SOURCE_ROUTES:raise ValueError('Hunter finite ordinary route')
 expected=SOURCE_ROUTES[run.identity]
 if run.graph.get('encounter')or run.graph['source_sha256']!=expected[1]or str(run.identity)not in run.catalog._data['routes']:raise ValueError('Hunter current source graph')
 if room is None and getattr(s,'application',None)is not None:
  dispatcher=s.application.world.dungeons;room=dispatcher.room(s)
 if room is None:
  if s.reward_run_id!=run.run_id or s.dungeon_participants!=frozenset((s.account.uid,)):raise ValueError('Hunter solo origin')
  members=(s,)
 else:
  if dispatcher is None:dispatcher=s.application.world.dungeons
  from els_server.domain.friends_dungeon import FriendsDungeons,Room
  from els_server.domain.friends_spawns import _checked_static_generation
  if (not isinstance(dispatcher,FriendsDungeons)or not isinstance(room,Room)or dispatcher is not s.application.world.dungeons
      or room.identity!=run.identity or room.phase not in ('active','part_end')or s not in room.members
      or not 2<=len(room.members)<=4 or room.party.get('run')is not room
      or room.party.get('difficulty',0)!=0 or room.party.get('mode',0)!=0
      or any(room.party.get(k)for k in ('raid_party','challenge','challenge_pending','solo_challenge'))):raise ValueError('Hunter ordinary party')
  _checked_static_generation(dispatcher,room);members=room.members
 paths=set();roster=[];bindings=[];static=[]
 seed=uuid.UUID(run.run_id)
 if str(seed)!=run.run_id or seed.version!=4:raise ValueError('Hunter source epoch')
 for member in members:
  a=member.account;r=member.dungeon_run;app=getattr(member,'application',None)
  if (not current_lease(member)or member.role!='game'or member.phase!='dungeon_active'or not member.dungeon_substage_synced
      or member.clear_notified or getattr(member,'dungeon_failed',False)or member.client_build!='dx11_260923'
      or not member.reward_test or not member.item_test or not member.drop_probe or not member.drop_test
      or not member.population_test or a.store is None or a.characters is None or a.store.uid!=a.uid or not _saved_paths(a)
      or getattr(member,'released',False)or getattr(member,'coop_error',False)or getattr(member,'social_overflow',False)
      or getattr(member,'reward_transaction',None)is not None or getattr(member,'active_challenge',None)is not None
      or getattr(member,'challenge_deadline',None)is not None
      or app is not None and(not app.registry.enabled(a.account_id)or app is not s.application)
      or r is None or (r.run_id,r.identity,r.stage,r.part,r.visits,r.graph['source_sha256'])!=(run.run_id,run.identity,run.stage,run.part,run.visits,run.graph['source_sha256'])):raise ValueError('Hunter current loaded actor')
  reward_id=str(uuid.uuid5(seed,'reward:'+str(a.uid)))if room is not None else run.run_id
  if member.reward_run_id!=reward_id:raise ValueError('Hunter owner reward epoch')
  path=Path(a.store.path).resolve();paths.add(path)
  if app is not None and path!=Path(app.config.state_file).resolve():raise ValueError('Hunter application database')
  roster.append(dict(owner=a.uid,account=a.account_id,connection=member.shop_session_id,reward_run=reward_id))
  b=_binding(member)
  generated=[dict(key=n['key'],source=n['hunter_source'],active=n['active'],team=n['team'],ally=n['ally'],no_drop=n['no_drop'],boss=n['boss'],hp=n['hp'],wire_sha=hashlib.sha256(n['wire']+n['init']).hexdigest())for n in r.current['npcs']if n.get('hunter_source')]
  bindings.append(tuple(id(b[n])for n in (0,1,2,3,8,9))+b[4:8]+(id(member),id(r),digest(generated),id(member.world_drops),member.world_drop_sequence,digest(member.world_drops),id(getattr(member,'mailbox',None))))
  projection=[(n['key'],n['template'],hashlib.sha256(n['wire']+n['init']).hexdigest())for n in r.current['npcs']if not n.get('dynamic')and not n.get('hunter_source')]
  if static and projection!=static:raise ValueError('Hunter original static roster diverged')
  static=projection
 if len(paths)!=1 or len({r['owner']for r in roster})!=len(roster):raise ValueError('Hunter database/roster uniqueness')
 context=dict(run_id=run.run_id,dungeon=run.identity,stage=run.stage,part=run.part,visits=run.visits,graph_sha256=run.graph['source_sha256'],roster=roster,static_roster=static)
 # JSON comparison remains stable between persisted lists and in-memory tuples.
 context=__import__('json').loads(storage.canonical(context))
 return members,room,next(iter(paths)),context,tuple(bindings)

def _guard(s,bound,dispatcher=None,room=None):
 def validate(db):
  if _checked(s,dispatcher,room)!=bound:raise ValueError('Hunter actor/source changed before commit')
  attached=db.execute('PRAGMA database_list').fetchall()
  if ([row[1]for row in attached if row[1]not in ('main','temp')]
      or Path(next(row[2]for row in attached if row[1]=='main')).resolve()!=bound[2]):raise ValueError('Hunter writer database')
  from els_server.storage.seal_quests import load_character,completed_ids
  from els_server.domain.region_quests import region_catalog
  storage.actors(db,bound[3])
  for member in bound[0]:
   character=load_character(db,member.account.uid,member.account.account_id)
   if not region_catalog().dungeon_allowed(bound[3]['dungeon'],character,completed_ids(db,member.account.uid)):raise ValueError('Hunter original region admission')
 return validate

def _boxes(members,s,deliveries):
 from els_server.domain.party_commands import _prepared_boxes
 return _prepared_boxes([(m,deliveries[m])for m in members if m is not s],deliveries[s])

def _apply_boxes(boxes):
 for member,box in boxes.items():member.mailbox=box

def loaded(s,event,*,dispatcher=None,room=None,randbelow=secrets.randbelow,broadcast_all=False):
 try:
  if (event.event_id!=0x202 or event.kind not in (0xb3,0xbb)or event.performers!=(0,)
      or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0):return []
  bound=_checked(s,dispatcher,room);members,room,path,context,_=bound
  run=s.dungeon_run
  # Optional scene population never changes a source condition/clear target.
  points=[n for n in run.current['npcs']if n['active']and not n['boss']and not n['no_drop']and not n.get('dynamic')and not n.get('hunter_source')and not n.get('ally')and n.get('team',1)!=0 and 'start_point'in n and 'offset'in n]
  if not points:return []
  from els_server.domain.dungeon_spawns import occupied_slots
  if any(occupied_slots(m)>=80 for m in members):return []
  keys=set().union(*(m.summon_keys for m in members));key=run.new_npc_keys(1,keys)[0]
  forbidden={code for part in run.parts.values()for condition in part['conditions']for code in condition.get('required',[])}
  code=-(2**31)
  while code in forbidden:code+=1
  anchor=min(points,key=lambda n:n['key'])
  source=dict(npc_key=key,template=grade(SOURCE_ROUTES[run.identity][0]),key_code=code,start_point=anchor['start_point'],offset=anchor['offset'],anchor_key=anchor['key'])
  staged={};deliveries={}
  def prepare(saved,replayed):
   if saved is None:return None
   if saved['context_sha256']!=digest(context):raise ValueError('Hunter source context')
   for member in members:
    existing=next((n for n in member.dungeon_run.current['npcs']if n.get('hunter_source')==saved),None)
    if existing is not None:staged[member]=None;deliveries[member]=[];continue
    if replayed:raise ValueError('Hunter generated actor was lost, refuse resurrection')
    if saved['npc_key']in member.dungeon_run.reserved_keys|member.summon_keys:raise ValueError('Hunter generated UID collision')
    actor,notice=wire.spawn(member.dungeon_run,saved);staged[member]=[*member.dungeon_run.current['npcs'],actor];deliveries[member]=[notice]
   if broadcast_all:
    from els_server.domain.party_commands import _prepared_boxes
    return _prepared_boxes([(m,deliveries[m])for m in members],[])
   return _boxes(members,s,deliveries)
  boxes=storage.generate(path,context,source,prepare,_guard(s,bound,dispatcher,room),randbelow=randbelow)
  if boxes is None:return []
  for member,npcs in staged.items():
   if npcs is not None:member.dungeon_run.current['npcs']=npcs
  _apply_boxes(boxes);return []if broadcast_all else deliveries[s]
 except (ValueError,sqlite3.Error,AttributeError,KeyError,TypeError):return []

def solo_loaded(s,event):
 # Shared barriers call loaded once after all original member cursors match.
 if s.reward_run_id!=s.dungeon_run.run_id:return []
 return loaded(s,event)

def _envelope(event):
 return event.event_id==0x202 and event.kind==0xad and event.performers==(0,)and event.uid==event.target_uid==2**64-1 and event.payload_mode==0

def accepted_death(s,event,*,dispatcher=None,room=None,randbelow=secrets.randbelow,now=None):
 from els_server.domain.dungeon_lifecycle import death_report,death_ack
 run=s.dungeon_run
 if run is None:return None
 try:death=death_report(event.payload)
 except ValueError:return None
 npc=next((n for n in run.current['npcs']if n['key']==death['index']),None)
 if npc is None or not npc.get('hunter_source'):return None
 try:
  bound=_checked(s,dispatcher,room);members,room,path,context,_=bound;source=npc['hunter_source'];validate=_guard(s,bound,dispatcher,room)
  participants={m.account.uid for m in members};hp=struct.unpack('>f',struct.pack('>I',death['hp_bits']))[0]
  if (not _envelope(event)or death['flag']not in (0,1)or not math.isfinite(hp)or hp<=0
      or any(death[k]not in participants for k in ('source','killer','last_uid'))
      or any(uid not in participants for k in ('contribution','readiness','counters')for uid in death[k])):return []
  for member in members:
   actor=next((n for n in member.dungeon_run.current['npcs']if n['key']==npc['key']),None)
   if actor!=npc or npc['key']in member.summon_keys:raise ValueError('Hunter source actor changed')
  plans={m.account.uid:dict(run_id=m.reward_run_id,stage=run.stage,part=run.part,visits=run.visits,npc_key=npc['key'],drop_id=m.world_drop_sequence,xyz=list(death['xyz'][3:]),ed=0)for m in members}
  deliveries={};worlds={}
  def prepare(results):
   gains={uid:r['xp']for uid,r in results.items()if r['xp']};notice=wire.death(npc['key'],death['killer'],gains)
   for member in members:
    reply=([death_ack()]if member is s else [])+[notice];world=dict(member.world_drops);entry=results.get(member.account.uid)
    if entry is not None:
     row=entry['drop'];drop_id=row['drop_id']
     if type(drop_id)is not int or not 1<=drop_id<2**31 or drop_id in world:raise ValueError('Hunter ground UID collision')
     from els_server.domain.dungeon_drops import ground_drop_notice
     cf=ground_drop_notice(drop_id,row['xyz'],uid=member.account.uid,template=row['template']);row['payload_hex']=cf.payload.hex();world[drop_id]=row
     reply+=[cf,*wire.level(member.account.uid,__import__('els_server.protocol.profession_messages',fromlist=['ProfessionState']).ProfessionState(**entry['before']),entry['after'])]
    worlds[member]=world;deliveries[member]=reply
   return _boxes(members,s,deliveries)
  result=storage.destroy(path,context,source,event.payload,plans,prepare,validate,now=time.time if now is None else now,randbelow=randbelow)
  if result['replayed']:
   # Current absolute saved state, outside the completed writer; never another
   # additive AF/CF/4C4 or roll. Authorization brackets every read and encoder.
   if _checked(s,dispatcher,room)!=bound:return []
   deliveries={m:([death_ack()]if m is s else [])+[m.saved_user_sync()]for m in members}
   boxes=_boxes(members,s,deliveries)
   if _checked(s,dispatcher,room)!=bound:return []
  else:
   boxes=result['prepared']
   for member in members:
    member.world_drops=worlds[member]
    entry=next((row for row in worlds[member].values()if row.get('source_run')==context['run_id']and row.get('npc_key')==npc['key']),None)
    if entry is not None:member.world_drop_sequence=max(member.world_drop_sequence,entry['drop_id']+1);member.world_drop_issued=entry
  for member in members:
   member.dungeon_run.defeated={**member.dungeon_run.defeated,npc['key']:bytes(event.payload)};member.defeated_npcs=member.dungeon_run.defeated
  _apply_boxes(boxes);return deliveries[s]
 except (ValueError,sqlite3.Error,AttributeError,KeyError,TypeError):return []

def claim(s,request,drop):
 if drop.get('source')!=POLICY:return None
 try:
  bound=_checked(s);members,room,path,context,_=bound
  run=s.dungeon_run;npc=next((n for n in run.current['npcs']if n['key']==drop['npc_key']),None)
  if (npc is None or not npc.get('hunter_source')or drop['source_run']!=run.run_id or drop['run_id']!=s.reward_run_id
      or drop['owner']!=s.account.uid or (drop['stage'],drop['part'],drop['visits'])!=(run.stage,run.part,run.visits)
      or hashlib.sha256(run.defeated.get(npc['key'],b'')).hexdigest()!=drop['death_sha256']):return []
  def prepare(items):
   from els_server.domain.dungeon_drops import ground_pickup_notice,pickup_inventory_notice
   reply=[Event(0x201,kind=0xd1,payload=bytes(4)),ground_pickup_notice(drop['drop_id'],s.account.uid,template=drop['template']),pickup_inventory_notice(items)]
   for event in reply:encode_event(event)
   return reply
  result=storage.claim(path,context,npc['hunter_source'],s.account.uid,request,prepare,_guard(s,bound))
  if result['replayed']:
   if _checked(s)!=bound:return []
   answer=[Event(0x201,kind=0xd1,payload=bytes(4)),s.saved_user_sync()]
   for event in answer:encode_event(event)
   if _checked(s)!=bound:return []
  else:answer=result['prepared']
  drop['pickup_committed']=True;s.pickup_receipt=dict(dungeon_run_id=s.reward_run_id,drop_id=drop['drop_id'],replayed=result['replayed'])
  return answer
 except __import__('els_server.storage.inventory_state',fromlist=['InventoryFull']).InventoryFull:return [Event(0x201,kind=0xd1,payload=struct.pack('>i',-1))]
 except (ValueError,sqlite3.Error,AttributeError,KeyError,TypeError):return []
