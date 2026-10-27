"""Original ordinary death/clear consumers with one writer for loaded participants."""
import copy,hashlib,json,sqlite3,struct,uuid
from pathlib import Path
from contextlib import closing
from els_server.domain import formal_pve_economy as rules
from els_server.domain.raid_economy_flow import application,_ShadowHP,_ADOPT,_clear_observers

_DEATH_SEAL=object()
class _DeathSource:
 """One original actor/writer delegates its validated finish to a private shadow.

 The existing generic AD decoder and static-actor checks run first. This
 avoids asking old solo loot gates to treat a shadow as an authenticated lease.
 No old lease check is weakened and no client field constructs this object.
 """
 __slots__=('seal','original','shadow','db','payload','guard')
 def __init__(self,seal,original,shadow,db,event,guard):
  if seal is not _DEATH_SEAL or not db.in_transaction or guard(db)is not True:raise ValueError('Ordinary prepared death writer')
  self.seal=seal;self.original=original;self.shadow=shadow;self.db=db;self.payload=event.payload;self.guard=guard

def prepared_death(s,event,npc,report,expired):
 source=getattr(s,'_formal_pve_death_source',None)
 if source is None:return None
 from els_server.domain.legacy_pve_exp import eligible
 if(type(source)is not _DeathSource or source.seal is not _DEATH_SEAL or source.shadow is not s or event.payload!=source.payload or not source.db.in_transaction or source.guard(source.db)is not True or expired or not eligible(npc)):raise ValueError('Ordinary exact prepared death source')
 original=source.original.dungeon_run;shadow=s.dungeon_run
 if(original is None or shadow is None or shadow.run_id!=original.run_id or shadow.graph is not original.graph or(shadow.stage,shadow.part,shadow.visits)!=(original.stage,original.part,original.visits)or not any(n is npc for n in shadow.current['npcs'])):raise ValueError('Ordinary original death consumer binding')
 before=next((n for n in original.current['npcs']if n['key']==npc['key']),None)
 if before is None or any(npc.get(k)!=before.get(k)for k in('template','source_index','active','boss','no_drop','team','ally')):raise ValueError('Ordinary prepared original NPC identity')
 from els_server.domain.dungeon_flow import finish_death
 from els_server.domain.dungeon_lifecycle import empty_reward_death_notice
 return finish_death(s,event,npc,report,False,empty_reward_death_notice(npc['key'],report['killer']))

def bind_story(s):
 if s.dungeon_id!=30000 or s.reward_run_id is None:return
 from els_server.domain.legacy_pve_exp import policy
 from els_server.domain.gm_rates import snapshot
 p=policy();row=p['maps']['30000'];rate=snapshot()['experience_bp'];base=p['levels'][str(row['npc_level'])]
 s._formal_story_exp=dict(epoch=s.reward_run_id,owner=s.account.uid,graph_sha256=row['graph_sha256'],policy=p['policy'],policy_sha256=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest(),npc_level=row['npc_level'],table_experience=base,experience_bp=rate,base_experience=min(2**31-1,base*rate//10000))

def _binding(members,room,phase):
 from els_server.domain.dungeon_hp_c1 import _lease
 from els_server.domain.friends_spawns import _checked_static_generation
 app=application(members[0]);paths=set();values=[];owners=frozenset(s.account.uid for s in members)
 if app is None or len(owners)!=len(members):raise ValueError('Ordinary actual Application/roster')
 if room is not None:
  if(tuple(room.members)!=members or room.phase!=phase or room.party.get('run')is not room or tuple(room.party['members'])!=members or any(room.party.get(k)for k in('raid_party','challenge','challenge_pending','solo_challenge'))):raise ValueError('Ordinary original loaded room')
  generation=_checked_static_generation(app.world.dungeons,room)if members[0].dungeon_run is not None else(room,room.seed,room.identity)
 else:
  if len(members)!=1 or app.world.dungeons.room(members[0])is not None:raise ValueError('Ordinary original solo epoch')
  generation=None
 for s in members:
  r=s.dungeon_run;mid=r.identity if r is not None else s.dungeon_id
  if rules.definition(mid)is None or(r is not None and rules.check_run(r)is None):raise ValueError('Ordinary finite original graph')
  if(application(s)is not app or s.role!='game'or s.client_build!='dx11_260923'or not _lease(s)or s.phase!='dungeon_active'or not s.dungeon_substage_synced or s.gate_stage_loading or s.clear_notified or s.dungeon_failed or not s.reward_test or not s.item_test or not s.drop_probe or s.account.store.uid!=s.account.uid or s.account.characters is None or s.account.reward_store.uid!=s.account.uid or getattr(s,'reward_transaction',None)is not None or getattr(s,'active_challenge',None)is not None or getattr(s,'challenge_deadline',None)is not None or getattr(s,'coop_error',None)or getattr(s,'social_overflow',False)or s.dungeon_participants!=owners):raise ValueError('Ordinary current actor unavailable')
  if app.config.mode=='friends'and not app.registry.enabled(s.account.account_id):raise ValueError('Ordinary current account disabled')
  if phase=='part_end'and not s.part_end_notified:raise ValueError('Ordinary actual end barrier')
  if room is None:
   if s in app.world.party_of or s in app.world.members or(r is not None and r.run_id!=s.reward_run_id):raise ValueError('Ordinary original solo membership')
  elif(app.world.dungeons.room(s)is not room or app.world.party_of.get(s)is not room.party or s in app.world.members or s.reward_run_id!=str(uuid.uuid5(uuid.UUID(room.seed),'reward:'+str(s.account.uid)))or(r is not None and r.run_id!=room.seed)):raise ValueError('Ordinary original group epoch')
  for p in(s.account.store.path,s.account.reward_store.path,s.account.characters.path,app.config.state_file):paths.add(Path(p).resolve())
  if r is None:
   b=getattr(s,'_formal_story_exp',None)
   if not s.population_test or not isinstance(b,dict)or b['epoch']!=s.reward_run_id or b['owner']!=s.account.uid or mid!=30000:raise ValueError('Ordinary original El Tree EXP binding')
   native=(s.gate_stage,0,s.gate_stage+1,json.dumps(b,sort_keys=True))
  else:native=(r.stage,r.part,r.visits,r.graph['source_sha256'],json.dumps(r.next,sort_keys=True),r.ready_at,json.dumps(r.legacy_experience,sort_keys=True))
  values.append((s,s.account,s.account.store,s.account.reward_store,s.account.characters,s.shop_session_id,s.account.account_id,s.account.uid,s.reward_run_id,r,native,tuple(sorted(s.defeated_npcs.items())),s.world_drop_sequence))
 if len(paths)!=1:raise ValueError('Ordinary original database differs')
 if len({v[10][:3]for v in values})!=1:raise ValueError('Ordinary original peer stage/part/visits differ')
 return tuple(values),generation,next(iter(paths))

def _guard(members,room,phase,bound,db):
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.bank_state import account_for
 if _binding(members,room,phase)!=bound:raise ValueError('Ordinary source generation/lease changed')
 main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
 if(not db.in_transaction or len(main)!=1 or Path(main[0][2]).resolve()!=bound[2]or db.execute('PRAGMA foreign_keys').fetchone()!=(1,)or any(r[1]not in('main','temp')for r in db.execute('PRAGMA database_list'))):raise ValueError('Ordinary exact original SQL writer')
 for s in members:
  require_active_character(db,s.account.uid)
  if account_for(db,s.account.uid)!=s.account.account_id:raise ValueError('Ordinary saved owner changed')
 return True

def _shadow(s):
 shadow=copy.copy(s);shadow.dungeon_clock=copy.copy(s.dungeon_clock);shadow.world_drops={k:dict(v)for k,v in s.world_drops.items()};shadow.defeated_npcs=dict(s.defeated_npcs)
 if s.dungeon_run is not None:
  r=s.dungeon_run;shadow.dungeon_run=copy.copy(r)
  for k,v in r.__dict__.items():
   if k not in('catalog','graph','clock','hp_context'):setattr(shadow.dungeon_run,k,copy.deepcopy(v))
  if r.hp_context is not None:shadow.dungeon_run.hp_context=_ShadowHP(r,shadow.dungeon_run)
  shadow.defeated_npcs=shadow.dungeon_run.defeated
 shadow._pve_internal=True;return shadow

def _adopt(s,shadow):
 if s.dungeon_run is not None:
  original=s.dungeon_run;hp=original.hp_context;original.__dict__.clear();original.__dict__.update(shadow.dungeon_run.__dict__);original.hp_context=hp
 for name in(*_ADOPT,'defeated_npcs','world_drops','world_drop_sequence','world_drop_issued'):
  if hasattr(shadow,name):setattr(s,name,getattr(shadow,name))
 if s.dungeon_run is not None:s.defeated_npcs=s.dungeon_run.defeated
 s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started

def _prepare_mailboxes(deliveries,requester,all_members=False):
 from els_server.domain.party_commands import _prepared_boxes
 snapshots=[(s,s.mailbox,s.mailbox.bytes,tuple(s.mailbox.messages),tuple(s.mailbox.moves.items()))for s,events in deliveries]
 boxes=_prepared_boxes([(s,[e for e in events if e.kind!=0xbc])for s,events in deliveries if all_members or s is not requester],next(events for s,events in deliveries if s is requester))
 return boxes,snapshots
def _mailboxes_unchanged(snapshots):
 for s,box,size,messages,moves in snapshots:
  if s.mailbox is not box or(box.bytes,tuple(box.messages),tuple(box.moves.items()))!=(size,messages,moves):raise ValueError('Ordinary precommit mailbox changed')

def _identity(s,npc):
 if s.dungeon_run is not None:
  from els_server.domain.legacy_pve_exp import identity
  return identity(s,npc)
 b=s._formal_story_exp
 from els_server.domain.dungeon_routes import route_catalog
 graph=route_catalog().graph(30000);sources=graph['stages'][str(s.gate_stage)]['parts']['0']['groups']
 matched=[n for group in sources for n in group['npcs']if n.get('template')==npc['template']and n['source_index']==npc['key']+1 and n['active']==npc['active']and n['no_drop']==npc['no_drop']]
 if len(matched)!=1:raise ValueError('El Tree exact original source index')
 return dict(owner=s.account.uid,run_id=s.reward_run_id,dungeon=30000,stage=s.gate_stage,part=0,visits=s.gate_stage+1,npc_key=npc['key'],template=npc['template'],source_index=matched[0]['source_index'],boss=bool(matched[0]['boss']),**{k:v for k,v in b.items()if k not in('epoch','owner')})

def _boss_source_witness(db,s):
 """Record the available native death-side evidence for the source receipt.

 The local reward source is the original complete clear consumer. Some native
 maps use a separate exit actor, so this diagnostic does not add a second
 unproven Boss-AD prerequisite to that original clear qualification.
 """
 mid=s.dungeon_run.identity if s.dungeon_run is not None else 30000
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pve_kill_experience'").fetchone():return False
 saved=set()
 for(raw,)in db.execute('SELECT identity_json FROM pve_kill_experience WHERE owner=? AND run_id=?',(s.account.uid,s.reward_run_id)):
  row=json.loads(raw)
  if row.get('boss')is True and row['dungeon']==mid and row['graph_sha256']==rules.definition(mid)['graph_sha256']and type(row.get('source_index'))is int:saved.add((row['stage'],row['part'],row['source_index'],row['template']))
 if s.dungeon_run is None:return(2,0,1,5)in saved
 from els_server.domain.legacy_pve_exp import eligible
 r=s.dungeon_run;required={(r.stage,part,n['source_index'],n['template'])for part,value in r.parts.items()for n in value['npcs']if n.get('boss')and eligible(n)}
 if required:return required<=saved
 # A terminal exit stage can follow a previously committed Boss stage. Keep
 # that exact source receipt requirement without guessing another Boss ID.
 return bool(saved)

def _kill_observer(db,s,shadow,npc,proof,guard):
 from els_server.domain.quest_flow import store,observed_run
 from els_server.storage.seal_quests import load_character
 r=observed_run(s);key=r.run_id+':'+str(r.stage)+':'+str(r.part)+':kill:'+str(npc['key'])
 level=getattr(s,'_quest_run_levels',{}).get(r.run_id,load_character(db,s.account.uid,s.account.account_id)['level'])
 events=store(s).record(key,dict(kind='kill',dungeon=r.identity,npc=npc['template'],level=level),proof,transaction=db,validate=guard)
 shadow._quest_seen_events=set(getattr(s,'_quest_seen_events',set()))|{key};return events

def _story_clear_observer(db,s,shadow,guard):
 from els_server.domain.quest_flow import store,observed_run
 from els_server.storage.seal_quests import load_character
 r=observed_run(s);key=r.run_id+':clear';level=getattr(s,'_quest_run_levels',{}).get(r.run_id,load_character(db,s.account.uid,s.account.account_id)['level'])
 events=store(s).record(key,dict(kind='clear',dungeon=30000,level=level,rank=None),(r.run_id+':'+r.graph['source_sha256']).encode(),transaction=db,validate=guard)
 shadow._quest_seen_events=set(getattr(s,'_quest_seen_events',set()))|{key};return events

def death(members,event,requester,room=None):
 from els_server.domain.dungeon_lifecycle import death_report,experience_death_notice
 from els_server.domain.legacy_pve_exp import eligible
 from els_server.storage.legacy_pve_exp import commit
 from els_server.domain import dungeon_flow
 from els_server.domain.local_session import LocalSession
 from els_server.protocol.protocol_codec import encode_event
 members=tuple(members);bound=_binding(members,room,'active');d=death_report(event.payload)
 if(event.event_id!=0x202 or event.kind!=0xad or event.performers!=(0,)or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0 or requester is not(members[0]if room is None else room.leader)):raise ValueError('Ordinary original accepted-death envelope')
 shadows=[];deliveries=[]
 with closing(sqlite3.connect(bound[2],timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard=lambda writer:_guard(members,room,'active',bound,writer);guard(db)
  for s in members:
   if s.dungeon_run is None:
    from els_server.domain.dungeon_population import population
    current=population(s.gate_stage,hp_context=getattr(s,'_c1_hp_context',None));npc=next((n for n in current['npcs']if n['key']==d['index']),None)
   else:npc=next((n for n in s.dungeon_run.current['npcs']if n['key']==d['index']),None)
   if npc is None or not eligible(npc)or npc['key']in s.defeated_npcs:raise ValueError('Ordinary new exact enemy source required')
   shadow=_shadow(s);shadow.reward_transaction=db
   shadow._formal_pve_death_source=_DeathSource(_DEATH_SEAL,s,shadow,db,event,guard)
   events=dungeon_flow.handle(shadow,event)if s.dungeon_run is not None else LocalSession._handle(shadow,event)
   if not any(e.kind==0xae for e in events)or shadow.defeated_npcs.get(npc['key'])!=event.payload:raise ValueError('Ordinary original consumer refused death')
   shadow.__dict__.pop('_formal_pve_death_source',None)
   # Preserve the exact original quest level before awarding this kill's EXP.
   notices=_kill_observer(db,s,shadow,npc,event.payload,guard)
   award=commit(db,s.account.reward_store,_identity(s,npc),event.payload,d['killer'])
   if award['replayed']:raise ValueError('Ordinary fresh source has historical kill receipt')
   events=[e for e in events if e.kind!=0xaf and(s is requester or e.kind!=0xae)]
   events.insert(1 if s is requester else 0,experience_death_notice(npc['key'],d['killer'],s.account.uid,award['experience']));events+=notices
   for e in events:encode_event(e)
   shadows.append(shadow);deliveries.append((s,events))
  boxes,snapshots=_prepare_mailboxes(deliveries,requester)if room is not None else({},[])
  guard(db);_mailboxes_unchanged(snapshots)
 for s,shadow in zip(members,shadows):_adopt(s,shadow)
 for s,box in boxes.items():s.mailbox=box
 if room is not None:application(requester).world.dungeons.part_wait(room)
 return next(events for s,events in deliveries if s is requester)

def clear(members,event,requester,room=None):
 from els_server.domain.local_session import LocalSession
 from els_server.storage.legacy_pve_exp import run_total
 from els_server.storage.seal_quests import load_character
 from els_server.domain.raid_reward_items import _issue_source
 from els_server.protocol.protocol_codec import encode_event
 members=tuple(members);bound=_binding(members,room,'part_end');shadows=[];deliveries=[]
 if(event.event_id!=0x202 or event.kind!=0xbb or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Ordinary full-clear envelope')
 for s in members:
  r=s.dungeon_run
  if(r is None and(s.gate_stage!=2 or event.payload!=b'\0'))or(r is not None and(not isinstance(r.next,dict)or r.next.get('kind')!=4 or event.payload!=struct.pack('>b',r.part)or r.ready_at is None or r.clock()<r.ready_at)):raise ValueError('Ordinary original final source barrier')
 with closing(sqlite3.connect(bound[2],timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard=lambda writer:_guard(members,room,'part_end',bound,writer);guard(db)
  for s in members:
   mid=s.dungeon_run.identity if s.dungeon_run is not None else 30000;before=load_character(db,s.account.uid,s.account.account_id)
   boss_proof=_boss_source_witness(db,s)
   from els_server.storage.elixir_economy import bonus as elixir_bonus
   bonus_context=dict(owner=s.account.uid,dungeon=mid,run_id=s.reward_run_id,graph_sha256=rules.definition(mid)['graph_sha256'])
   previous=bool(db.execute('SELECT 1 FROM reward_receipts WHERE run_id=?',(s.reward_run_id,)).fetchone())
   drop_bp=elixir_bonus(db,s.account.uid,mid,'drop','elixir-clear:'+s.reward_run_id,bonus_context,already_issued=previous)
   plan=rules.clear_items(mid,s.reward_run_id,s.account.uid,before,group=room is not None,drop_bp=drop_bp)
   # Compatible recovery closes only new Aurora ticket production. A run with
   # a committed original receipt still derives its exact saved source plan.
   if mid in (34510,34520) and not previous:
    from els_server.domain.aurora_ticket_rules import enabled as aurora_enabled
    if not aurora_enabled():plan=[row for row in plan if row['template']!=711786]
   experience=rules.clear_bonus(run_total(db,s.account.uid,s.reward_run_id,clear_basis=True))
   # These two ordinary original maps already had a guaranteed solo fragment
   # clear branch. Preserve that independent reward through the new writer.
   from els_server.domain.dungeon_equipment_loot_rules import MAPS as equipment_maps,catalog as equipment_policy,inventory_plan
   if room is None and mid in equipment_maps:plan.append(inventory_plan(118445,equipment_policy()['values']['fragment_on_validated_clear']))
   source=dict(policy_sha256=rules.policy()['_sha256'],reward_source='local-full-native-clear-current-display-pool',dungeon=mid,run=s.reward_run_id,owner=s.account.uid,graph_sha256=rules.definition(mid)['graph_sha256'],native_final_stage=s.dungeon_run.stage if s.dungeon_run is not None else 2,committed_original_boss_source=boss_proof,roster=sorted(m.account.uid for m in members))
   if any(x['template']in(135911,136174)for x in plan):source['group_clear']=room is not None
   cap=_issue_source(db,s.account.uid,s.reward_run_id,'ordinary',source,plan,guard)if plan else None
   from els_server.domain.random_mission_flow import prepare_clear as prepare_mission_clear,finish_clear as finish_mission_clear
   mission=prepare_mission_clear(s,db,experience,members,room,bound)
   shadow=_shadow(s);shadow.reward_transaction=db;shadow._raid_phase_internal=True
   from els_server.domain.ariel_daily_special import prepare as prepare_daily_special
   supply=dict(owner=shadow,original_session=s,transaction=db,plan=plan,source=cap,experience=experience,daily_special=prepare_daily_special(s),random_mission=mission)
   shadow._raid_supply=supply;shadow._pve_clear_supply=supply
   events=LocalSession._handle(shadow,event)
   if not shadow.clear_notified or shadow.reward_receipt is None:raise ValueError('Ordinary original clear refused')
   events+=finish_mission_clear(mission,db)
   events=[e for e in events if e.kind!=0xbc or s is requester]
   if s.dungeon_run is None:events+=_story_clear_observer(db,s,shadow,guard)
   else:_clear_observers(db,s,shadow,before,events,guard)
   for e in events:encode_event(e)
   shadows.append(shadow);deliveries.append((s,events))
  boxes,snapshots=_prepare_mailboxes(deliveries,requester,all_members=True)if room is not None else({},[])
  guard(db);_mailboxes_unchanged(snapshots)
 for s,shadow in zip(members,shadows):_adopt(s,shadow)
 for s,box in boxes.items():s.mailbox=box
 return next(events for s,events in deliveries if s is requester)

def solo(s,event):
 if getattr(s,'_pve_internal',False)or event.event_id!=0x202 or event.kind not in(0xad,0xbb):return None
 mid=s.dungeon_run.identity if s.dungeon_run is not None else s.dungeon_id
 if rules.definition(mid)is None:return None
 app=application(s)
 if app is None or app.world.dungeons.room(s)is not None:return None
 if s.phase!='dungeon_active'or s.clear_notified:return None
 if event.kind==0xad:
  if s.dungeon_run is not None:return None
  from els_server.domain.dungeon_lifecycle import death_report
  try:d=death_report(event.payload)
  except ValueError:return []
  if d['index']in s.defeated_npcs:return None
  from els_server.domain.dungeon_population import population
  from els_server.domain.legacy_pve_exp import eligible
  npc=next((n for n in population(s.gate_stage,hp_context=getattr(s,'_c1_hp_context',None))['npcs']if n['key']==d['index']),None)
  if npc is None or not eligible(npc):return None
  try:return death((s,),event,s)
  except(ValueError,sqlite3.Error,OverflowError,struct.error):return []
 r=s.dungeon_run
 if not s.part_end_notified or(r is not None and(not isinstance(r.next,dict)or r.next.get('kind')!=4))or(r is None and s.gate_stage!=2):return None
 try:return clear((s,),event,s)
 except(ValueError,sqlite3.Error,OverflowError,struct.error):return []

def group_death(dispatcher,room,s,event):
 if rules.definition(room.identity)is None:return None
 if room.phase!='active'or s is not room.leader:return None
 from els_server.domain.dungeon_lifecycle import death_report
 from els_server.domain.legacy_pve_exp import eligible
 try:d=death_report(event.payload)
 except ValueError:return []
 if s.dungeon_run is None:
  from els_server.domain.dungeon_population import population
  npcs=population(s.gate_stage,hp_context=getattr(s,'_c1_hp_context',None))['npcs']
 else:npcs=s.dungeon_run.current['npcs']
 npc=next((n for n in npcs if n['key']==d['index']),None)
 if npc is None or not eligible(npc)or npc['key']in s.defeated_npcs:return None
 try:return death(tuple(room.members),event,s,room)
 except(ValueError,sqlite3.Error,OverflowError,struct.error):return []
