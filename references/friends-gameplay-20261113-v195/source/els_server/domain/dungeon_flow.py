"""Native solo lifecycle for source-driven static dungeon routes.
Unverified scripted encounters are rejected at admission, never auto-cleared.
"""
from els_server.domain.dungeon_result_rules import prepare_clear as prepare_result_clear
from els_server.domain.clear_ed_display import amount as result_ed

import copy,functools,hashlib,json,math,struct,time
from dataclasses import replace
from els_server.paths import PROJECT_ROOT
from els_server.protocol.protocol_codec import Event
from els_server.domain.dungeon_lifecycle import death_envelope,death_report,death_ack,empty_reward_death_notice,part_end_notice
from els_server.anti_cheat import dungeon_signal
from els_server.domain.reward_rules import item_plan
from els_server.domain.ground_currency import coin_template

SHADOW_CASTLE_GRAPH='3239dda07b43a5705f1a21ecbf3bf0f8c05ad4419b7ec3447170003e7affabee'
# In both castle worlds the odd triggers enable the original platform
# meshes and collision lines. The boss world's trigger table is separate.
SHADOW_CASTLE_PLATFORMS={1:range(1,86,2),3:range(1,56,2)}


def stage_platforms(run):
 if run.identity!=34800 or run.graph['source_sha256']!=SHADOW_CASTLE_GRAPH:return []
 return [Event(0x201,kind=0x30c,payload=struct.pack('>i',trigger))
         for trigger in SHADOW_CASTLE_PLATFORMS.get(run.stage,())]


@functools.lru_cache(maxsize=1)
def local_rewards():
 r=json.loads((PROJECT_ROOT/'config/dungeon_local_rules.json').read_text(encoding='utf8'))
 if r['schema_version']!=1 or r['provenance']!='local_policy':raise ValueError('Dungeon local reward provenance')
 if any(type(r[k]) is not int or not 0<=r[k]<=2**31-1 for k in ('clear_ed','clear_experience','ordinary_ed','boss_ed')):raise ValueError('Local dungeon reward bound')
 return {**r,'items':[item_plan(**i) for i in r['clear_items']]}

_FINALE_ROOMS={35320:(3,0,'696e2f7ad0e4685ea9dea807e03bf7eb54a953c7d9b08453deae8bb0dcba79e3'),
 35321:(2,0,'1861ded3d8a7e8d67475e98a27449215227de7b19f907f3943675fa9ddad4e16'),
 35322:(0,0,'d110b77689c39fd9db46b26c8ae24894bb2bdb747fb4aea53ab2f4e2f3f36050')}

def finale_boss_pending(run):
 # Keep the resource's actual part. Never synthesize an absent boss-area part.
 spec=_FINALE_ROOMS.get(run.identity)
 if spec is None or (run.stage,run.part)!=spec[:2]:return False
 if run.graph['source_sha256']!=spec[2] or run.graph!=run.catalog.graph(run.identity):return True
 bosses=[n for n in run.current['npcs'] if n['template']==9431]
 return not bosses or any(n['key'] not in run.defeated for n in bosses)

def periodic(session):
 s=session
 if (s.dungeon_run is not None and s.phase=='dungeon_active' and not s.clear_notified
     and getattr(s,'challenge_deadline',None) is not None and time.time()>=s.challenge_deadline):return failed(s)
 if (s.dungeon_run is None or s.phase!='dungeon_active' or not s.dungeon_substage_synced
     or s.part_end_notified or s.clear_notified or curtain_token(s) is not None):return []
 if getattr(s.dungeon_run,'memory1_quest_barrier',frozenset())-set(s.dungeon_run.defeated):return []
 from els_server.domain.story_controller_retirements import gate_predecessor_blocked
 if gate_predecessor_blocked(s.dungeon_run):return []
 from els_server.domain.devildom1_raid2_controllers import gate_blocked
 if gate_blocked(s.dungeon_run) or finale_boss_pending(s.dungeon_run):return []
 if s.dungeon_run.poll_ready():
  if s.dungeon_run.next['kind']==0:
   # B7 opens the next sub-part without moving players. B8 reports arrival
   # at its start line; only then may BA load it and BB/BD start its actors.
   from els_server.protocol.dungeon_messages import initial_part
   message=initial_part(s.dungeon_run.next['part'])
   from els_server.protocol.protocol_codec import encode_event
   encode_event(message)
   # This pending transition is already copied by all prepared-death adopters.
   # Copy the target: never mutate the source condition/catalogue dictionary.
   s.dungeon_run.next={**s.dungeon_run.next,'curtain_opened':True}
   return [message]
  s.part_end_notified=True;s.dungeon_clock.pause()
  return [part_end_notice(s.dungeon_run.part)]
 return []

def handle(s,event,request_sequence=None):
 run=s.dungeon_run
 if run is None or s.phase!='dungeon_active' or event.event_id!=0x202:return None
 if run.chaos is not None:
  from els_server.protocol.henir_chaos_messages import SELECT as CHAOS_SELECT
  from els_server.storage.henir_chaos import REWARD_STAGE
  if event.kind==CHAOS_SELECT:
   from els_server.domain.henir_chaos_flow import select
   return select(s,event,run)
  if event.kind==0xad and run.stage==REWARD_STAGE and not run.chaos.selected:return []
 if event.kind==0x471:
  shadow,replies=prepare_condition_clear(s,event)
  if shadow is not None:adopt_condition_clear(s,shadow)
  return replies
 from els_server.domain.native_line_triggers import handle as line_trigger
 trigger_reply=line_trigger(s,event,request_sequence)
 if trigger_reply is not None:return trigger_reply
 # Guard before the raid settlement dispatch, including a direct BB.
 from els_server.domain.devildom1_raid2_controllers import gate_blocked
 if (event.kind==0xbb and not s.clear_notified and not getattr(s,'dungeon_failed',False)
     and (gate_blocked(run) or finale_boss_pending(run))):return []
 from els_server.domain.raid_economy_flow import solo as raid_phase_solo
 raid_reply=raid_phase_solo(s,event)
 if raid_reply is not None:return raid_reply
 if event.kind==0xb8:
  contact=curtain_contact(s,event)
  if contact is not None:
   reply=[Event(0x201,kind=0xb9,payload=bytes(4))]
   if getattr(s,'curtain_arrival',None)!=contact:
    reply.append(part_end_notice(contact[-1]))
    from els_server.protocol.protocol_codec import encode_event
    for message in reply:encode_event(message)
    s.curtain_arrival=contact;s.part_end_notified=True;s.dungeon_clock.pause()
   return reply
  # Current 1044A10 -> 1117280 -> 3B6DA30 writes one part byte.
  # B9 -> Game v600=1044B20 consumes an i32 result, removes its wait.
  # BB/BC can advance the native part before its queued B8 is emitted.
  # 1044A25 reads the part at send time, so either end of the last proven
  # transition may be reported. Acknowledging it must not open the new gate.
  transition=run.completed_transition
  late=(transition is not None and (run.stage,run.part,run.visits)==transition['target']
        and event.payload in transition['parts'])
  from els_server.domain.dungeon_equipment_loot_flow import current_lease
  owned=(event.performers in ((),(0,)) and event.uid==event.target_uid==2**64-1
         and event.payload_mode==0 and current_lease(s))
  valid=(owned and s.dungeon_substage_synced and not s.clear_notified
         and not getattr(s,'dungeon_failed',False) and event.payload==struct.pack('>b',run.part))
  # B9 invokes native CreateCurtain (1076BC0) for the arrived sub-part.
  return [Event(0x201,kind=0xb9,payload=struct.pack('>i',0 if valid or owned and late else 1836))]
 if event.kind==0xad:
  if not death_envelope(event):
   dungeon_signal(s,'invalid_dungeon_death_envelope')
   return []
  from els_server.domain.scene_actor_retirements import request_retry
  if not s.clear_notified and not getattr(s,'dungeon_failed',False):
   story_retry=request_retry(s,event,request_sequence)
   if story_retry is not None:return story_retry
  from els_server.domain.native_script_loot import accepted_death as script_reward_death
  script_reply=script_reward_death(s,event)
  if script_reply is not None:return script_reply
  try:d=death_report(event.payload)
  except ValueError:
   dungeon_signal(s,'malformed_dungeon_death')
   return []
  # C1/failure closes the HP lease. A late native report must not consult
  # population/HP or enter any economic writer after that closure.
  if s.clear_notified or getattr(s,'dungeon_failed',False):
   return [death_ack()]
  story_retry=request_retry(s,event,request_sequence,report=d)
  if story_retry is not None:return story_retry
  # Stage-local accepted ADs remain retryable after a sub-part transition.
  # This is an ACK of the original bytes, never another death or award.
  if (run.defeated.get(d['index'])==event.payload
      and not any(n['key']==d['index']for n in run.current['npcs'])):
   from els_server.domain.dungeon_equipment_loot_flow import current_lease
   if s.role=='game' and current_lease(s):
    return [death_ack()]
  # Finite static-controller adapters must not consume an already admitted
  # dynamic actor's original expiry. Retain the existing expiry decoder and
  # exact server-allocated identity; zero is never an alias for another actor.
  from els_server.domain.hunter_chest_flow import accepted_death as hunter_death
  hunter_reply=hunter_death(s,event)
  if hunter_reply is not None:return hunter_reply
  from els_server.domain.giant_misc_loot import accepted_retirement as giant_retirement
  retired=giant_retirement(s,event)
  if retired is not None:return retired
  retired=source_actor_expiry(s,event,d)
  if retired is not None:return retired
  actor=next((n for n in run.current['npcs'] if n['key']==d['index']),None)
  if actor is None and d['flag']==255:
   # A curtain changes the current part, not the B2 actor population.
   actor=next((n for part in run.parts.values()for n in part['npcs']
       if n['key']==d['index']and n.get('dynamic')),None)
  from els_server.domain.summons import valid_sentry_death
  from els_server.domain.scene_actor_retirements import dynamic_retirement_shape
  dynamic_expiry=actor is not None and actor.get('dynamic') and dynamic_retirement_shape(run,actor,d,(s.account.uid,))
  if dynamic_expiry:
   from els_server.domain.dungeon_equipment_loot_flow import current_lease
   if (s.role!='game' or not current_lease(s) or s.clear_notified
       or getattr(s,'reward_transaction',None) is not None or getattr(s,'reward_run_id',None)!=run.run_id
       or frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))!=frozenset((s.account.uid,))):return []
  else:
   from els_server.domain.lithia_memory1_retirements import handle as memory1_retirement
   retired=memory1_retirement(s,event,d)
   if retired is not None:return retired
   from els_server.domain.scene_actor_retirements import handle as scene_retirement
   retired=scene_retirement(s,event,d,request_sequence)
   if retired is not None:return retired
   from els_server.domain.story_controller_retirements import handle as story_retirement
   retired=story_retirement(s,event,d,request_sequence)
   if retired is not None:return retired
  from els_server.domain.devildom1_raid2_controllers import handle as raid_controller_retirement
  retired=raid_controller_retirement(s,event,d)
  if retired is not None:return retired
  if d['index'] in s.summon_keys:return None
  npc=actor
  hp=struct.unpack('>f',struct.pack('>I',d['hp_bits']))[0]
  participants=getattr(s,'dungeon_participants',frozenset((s.account.uid,)))
  # Inactive script controllers can report their own destruction without a
  # player killer. They still require a declared current actor and a native
  # death payload; hostile combat actors retain participant-only identity.
  scripted=npc is not None and not npc['active'] and (npc['no_drop'] or npc.get('ally'))
  from els_server.domain.summons import valid_sentry_death
  expired=dynamic_expiry
  identities=participants|frozenset((0,2**64-1,2**64-4)) if expired else participants|frozenset((0,2**64-1)) if scripted else participants
  if (npc is None or not s.dungeon_substage_synced or d['flag'] not in (0,1) and not expired
      or any(d[name] not in identities for name in ('source','killer','last_uid'))
      or any(uid not in participants for name in ('contribution','readiness','counters') for uid in d[name])
       or not math.isfinite(hp) or hp<=0 and not expired):
   if npc is not None and npc['active'] and not npc['no_drop'] and not npc.get('ally') and d['flag'] in (0,1):
    dungeon_signal(s,'invalid_dungeon_death',actor_id=npc['key'])
   return []
  # Native scripts can set an actor's maximum HP after initialization. The
  # local single-player prototype trusts authenticated death reports; it does
  # not claim authoritative damage simulation from a matching max-HP scalar.
  previous=run.defeated.get(npc['key'])
  if previous is not None:
   if previous==event.payload:return [death_ack()]
   if npc['active'] and not npc['no_drop'] and not npc.get('ally') and d['flag'] in (0,1):
    dungeon_signal(s,'conflicting_dungeon_death',actor_id=npc['key'])
   return []
  if s.clear_notified:return []
  if expired and not any(n is npc for n in run.current['npcs']):
   # Retire the still-loaded old actor without running the new part's gate
   # or any kill/reward observer. Serialize before committing its receipt.
   reply=[death_ack(),empty_reward_death_notice(npc['key'],d['killer'])]
   from els_server.protocol.protocol_codec import encode_event
   for message in reply:encode_event(message)
   run.defeated={**run.defeated,npc['key']:bytes(event.payload)}
   npc['active']=False;s.defeated_npcs=run.defeated
   return reply
  from els_server.domain.pve_economy_flow import prepared_death
  prepared=prepared_death(s,event,npc,d,expired)
  if prepared is not None:return prepared
  from els_server.domain.dungeon_equipment_loot_flow import accepted_death
  loot_reply=accepted_death(s,event,npc,d,expired)
  if loot_reply is not None:return loot_reply
  from els_server.domain.legacy_pve_exp import accepted_death as experience_death
  xp_reply=experience_death(s,event,npc,d,expired,finish_death)
  if xp_reply is not None:return xp_reply
  from els_server.domain.giant_misc_loot import accepted_death as giant_misc_death
  giant_reply=giant_misc_death(s,event,npc,d,expired,finish_death)
  if giant_reply is not None:return giant_reply
  return finish_death(s,event,npc,d,expired,empty_reward_death_notice(npc['key'],d['killer']))
 if event.kind==0xb3:
  if len(event.payload)!=9 or event.payload[:5]!=bytes(5):return []
  value=struct.unpack_from('>f',event.payload,5)[0]
  if not math.isfinite(value) or not 0<=value<=1e9:return []
  reply=[Event(0x201,kind=0xb4,payload=bytes(4)),Event(0x201,kind=0xb5,payload=struct.pack('>iQ',0,s.account.uid))]
  from els_server.domain.normal_fatigue_flow import loaded as fatigue_loaded
  try:reply+=fatigue_loaded(s,event)
  except(ValueError,__import__('sqlite3').Error):return[]
  if not s.dungeon_substage_synced:
   from els_server.protocol.dungeon_messages import initial_part,begin_substage
   # The native dungeon state accepts CCB after loading, before actors start.
   mirror_offer=getattr(run,'silver_mirror_offer',None)
   if mirror_offer is not None:reply.append(mirror_offer)
   reply.extend([Event(0x201,kind=0xb6,payload=bytes(16)),initial_part(run.part),begin_substage(run.part,npc_entries=((n['key'],n['template']) for n in run.current['npcs']))])
   reply.extend(stage_platforms(run))
   from els_server.domain.henir_flow import initialize as henir_supplies
   if run.identity==38100 and run.round==0:reply+=henir_supplies(s)
   s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.dungeon_clock.resume();run.loaded()
  from els_server.domain.hunter_chest_flow import solo_loaded
  return reply+solo_loaded(s,event)+periodic(s)
 if event.kind==0xbb:
  if curtain_loaded_retry(s,event):return [Event(0x201,kind=0xbc,payload=bytes(4))]
  curtain=curtain_token(s)
  if curtain is not None:
   if (not curtain_loading(s,curtain)
       or event.payload not in (struct.pack('>b',run.part),struct.pack('>b',curtain[-1]))):return []
   # Keep the original source cursor for fatigue and the prepared transition.
   event=replace(event,payload=struct.pack('>b',run.part))
  if len(event.payload)!=1:return []
  part=struct.unpack('>b',event.payload)[0]
  if part!=run.part or s.gate_stage_loading:
   return [Event(0x201,kind=0xbc,payload=bytes(4))] if part==getattr(s,'previous_dungeon_part',None) else []
  if not s.part_end_notified:return []
  reply=[Event(0x201,kind=0xbc,payload=bytes(4))]
  if s.clear_notified:return reply
  from els_server.domain.story_controller_retirements import gate_predecessor_blocked
  if gate_predecessor_blocked(run):return []
  if not run.poll_ready():return []
  if run.chaos is not None and run.stage!=REWARD_STAGE:
   if (event.performers not in ((),(0,)) or event.uid!=event.target_uid
       or event.uid!=2**64-1 or event.payload_mode!=0):return []
   from els_server.domain.henir_chaos_flow import transition
   try:return reply+transition(s,run)
   except (ValueError,__import__('sqlite3').Error):return []
  if run.identity in (38100,35880):
   from els_server.domain.equipment_engrave_flow import current_lease
   from els_server.storage.henir_force_rewards import issue as issue_henir
   def henir_authority():
    return bool(current_lease(s)and s.role=='game'and 0x28 in s.completed and s.phase=='dungeon_active'and s.dungeon_run is run and s.reward_run_id==run.run_id and s.part_end_notified and not s.clear_notified and not getattr(s,'dungeon_failed',False)and run.poll_ready()and len(getattr(s,'dungeon_participants',(s.account.uid,)))==1)
   reply+=issue_henir(s.account.store.path,s.account.uid,s.account.account_id,run,authorize=henir_authority)
  source=(run.stage,run.part,run.visits)
  target=run.next
  if target['kind']==4:
   run.completed_transition=dict(target=source,parts=(struct.pack('>b',run.part),))
   reply.extend(clear(s));return reply
  # Prepare the stage before committing the cursor so encoding failure does
  # not discard the completed part; the fixed run seed preserves retry bytes.
  from els_server.domain.normal_fatigue_flow import loaded as fatigue_loaded
  try:reply+=fatigue_loaded(s,event)
  except(ValueError,__import__('sqlite3').Error):return[]
  s.previous_dungeon_part=run.part;transition=run.advance();s.gate_stage=run.stage
  run.completed_transition=dict(target=(run.stage,run.part,run.visits),parts=tuple({struct.pack('>b',source[1]),struct.pack('>b',run.part)}))
  s.part_end_notified=False;s.defeated_npcs=run.defeated
  if transition=='stage':
   # 103E610 -> Game v1F0 keeps native reason3 player summons in dungeons;
   # BD -> 1041040 moves living owned summons through each player's v14F8.
   # Keep identity, expiry and request records; never respawn or restart AI.
   s.dungeon_substage_synced=False;s.gate_stage_loading=True
   reply.append(run.population_event())
  else:
   from els_server.protocol.dungeon_messages import initial_part,begin_substage
   if curtain is None:reply.append(initial_part(run.part))
   reply.append(begin_substage(run.part,npc_entries=((n['key'],n['template']) for n in run.current['npcs'])))
   s.dungeon_clock.resume();run.loaded()
  from els_server.domain.hunter_chest_flow import solo_loaded
  return reply+solo_loaded(s,event)+periodic(s)
 return None

def curtain_token(s):
 run=s.dungeon_run
 if run is None or run.next is None or run.next['kind']!=0 or run.next.get('curtain_opened') is not True:return None
 return (run.run_id,run.stage,run.part,run.visits,run.next['part'])

def curtain_contact(s,event):
 token=curtain_token(s)
 if token is None:return None
 from els_server.domain.dungeon_equipment_loot_flow import current_lease
 if (event.event_id==0x202 and event.kind==0xb8 and event.performers in ((),(0,))
     and event.uid==event.target_uid==2**64-1 and event.payload_mode==0
     and s.role=='game' and s.phase=='dungeon_active' and s.dungeon_substage_synced
     and not s.clear_notified and not getattr(s,'dungeon_failed',False)
     and current_lease(s) and event.payload==struct.pack('>b',token[-1])):return token
 return None

def curtain_loading(s,token):
 if not s.part_end_notified:return False
 if getattr(s,'curtain_arrival',None)==token:return True
 app=getattr(s,'application',None)
 if app is None:return False
 room=app.world.dungeons.room(s)
 from els_server.domain.known_resurrection_flow import accepted_dead
 return bool(room is not None and room.phase=='part_end' and s in room.members
             and accepted_dead(s,s.dungeon_run.run_id,room))

def curtain_loaded_retry(s,event):
 token=getattr(s,'curtain_arrival',None);run=s.dungeon_run
 transition=run.completed_transition
 return bool(token is not None and not s.part_end_notified and transition is not None
             and transition['target']==(run.stage,run.part,run.visits)
             and (run.run_id,run.stage,run.visits,run.part)==(token[0],token[1],token[3],token[-1])
             and event.event_id==0x202 and event.kind==0xbb
             and event.payload==struct.pack('>b',run.part))

def prepare_condition_clear(s,event):
 # 1044750 / 1116EE0: i32 stage, i32 part, u16 zero,
 # vector<bool> (DB8AE0), bool. B8 is the curtain request, not CC5 contact.
 # C26FFC reads seven i32s; 1044910 consumes result/type and source stage/part.
 run=s.dungeon_run;raw=event.payload
 source=struct.unpack_from('>ii',raw) if len(raw)>=8 else (run.stage,run.part)
 def reply(result,kind=0):
  return Event(0x201,kind=0x472,payload=struct.pack('>7i',result,kind,0,*source,0,0))
 error=(None,[reply(1836)])
 from els_server.domain.dungeon_equipment_loot_flow import current_lease
 if (event.event_id!=0x202 or event.kind!=0x471 or event.performers!=(0,)
     or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
     or s.role!='game' or s.phase!='dungeon_active' or not s.dungeon_substage_synced
     or getattr(s,'dungeon_failed',False) or not current_lease(s)
     or getattr(s,'reward_transaction',None) is not None or len(raw)<15):return error
 stage,part,reserved,count=struct.unpack_from('>iiHI',raw)
 conditions=run.current['conditions']
 if ((stage,part)!=(run.native_stage,run.part) or reserved!=0 or count!=len(conditions)
     or len(raw)!=15+count or raw[-1]not in (0,1) or any(v not in (0,1) for v in raw[14:-1])):return error
 shadow=copy.copy(s);shadow.dungeon_run=copy.copy(run);shadow.dungeon_clock=copy.copy(s.dungeon_clock)
 if run.hp_context is not None:
  from els_server.domain.raid_economy_flow import _ShadowHP
  shadow.dungeon_run.hp_context=_ShadowHP(run,shadow.dungeon_run)
 selected=None
 for flag,condition in zip(raw[14:-1],conditions):
  if not flag:continue
  shadow.dungeon_run.portal_requested=condition['kind']==5 or run.portal_requested
  if shadow.dungeon_run.condition_ready(condition):selected=condition;break
 if selected is None:
  if not s.clear_notified:
   from els_server.domain.combat_audit import early_timed_condition
   early_timed_condition(s,run,raw[14:-1])
  return error
 if s.clear_notified:
  # C1 can precede the native final-room condition request. Acknowledge
  # that already-authoritative completion without rerunning settlement.
  if not s.part_end_notified or run.next is None or run.next['kind']!=4:return error
  message=reply(0,4)
  from els_server.protocol.protocol_codec import encode_event
  encode_event(message)
  return s,[message]
 notifications=periodic(shadow)
 if shadow.dungeon_run.next is None:return error
 replies=[reply(0,shadow.dungeon_run.next['kind']),*notifications]
 from els_server.protocol.protocol_codec import encode_event
 for message in replies:encode_event(message)
 return shadow,replies

def adopt_condition_clear(s,shadow):
 for name in ('portal_requested','next','ready_at'):
  setattr(s.dungeon_run,name,getattr(shadow.dungeon_run,name))
 s.part_end_notified=shadow.part_end_notified
 s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started


# Native observed actor instances only: 20261025-193058 (keys 15/17) and
# 20261025-165751 (key 4). Other sources/maps/templates remain combat actors.
# Code-first recovery: disable only this finite new admission.
MEMORY8_SOURCE_ACTOR_EXPIRY_ENABLED=True
_MEMORY8_EXPIRY_GRAPH='696e2f7ad0e4685ea9dea807e03bf7eb54a953c7d9b08453deae8bb0dcba79e3'
_MEMORY8_EXPIRIES={
 (0,1,15):(9436,4,12,'LITHIA_MEMORY8_BUG.lua','a5d1caf39396087d781e2475f4078908eb3e30a031d593a8dab758ec183c3f16'),
 (0,1,17):(9436,6,37,'LITHIA_MEMORY8_BUG.lua','a5d1caf39396087d781e2475f4078908eb3e30a031d593a8dab758ec183c3f16'),
 (1,0,4):(9433,5,26,'LITHIA_MEMORY8_PLANT_DROSERA.lua','82f6b52a62d2bb6ed56f8f595a0875c5f7b421bd201774814a5856e4513d243c'),
}

def source_actor_expiry(s,event,report):
 """Acknowledge an observed original 255 without kill/quest/loot consumers.

 The shadow prepares the gate and encodes every reply before adopting any
 state. A byte-identical retry acknowledges only its original actor.
 """
 run=s.dungeon_run
 if not MEMORY8_SOURCE_ACTOR_EXPIRY_ENABLED:return None
 if run.identity!=35320 or report['flag']!=255:return None
 rule=_MEMORY8_EXPIRIES.get((run.stage,run.part,report['index']))
 if rule is None:return None
 template,source_index,point,script,script_sha=rule
 npc=next((n for n in run.current['npcs'] if n['key']==report['index']),None)
 from els_server.domain.summons import valid_sentry_death
 from els_server.domain.dungeon_equipment_loot_flow import current_lease
 if (npc is None or event.event_id!=0x202 or event.kind!=0xad or event.performers!=(0,) or event.uid!=2**64-1 or event.target_uid!=2**64-1
     or event.payload_mode!=0 or s.role!='game' or s.phase!='dungeon_active' or not s.dungeon_substage_synced
     or s.clear_notified or not current_lease(s) or getattr(s,'reward_transaction',None) is not None
     or getattr(s,'reward_run_id',None)!=run.run_id
     or frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))!=frozenset((s.account.uid,))
     or s.account.character()['unit_type']!=15 or not valid_sentry_death(report,s.account.uid)
     or run.graph['source_sha256']!=_MEMORY8_EXPIRY_GRAPH or run.graph!=run.catalog.graph(run.identity)
     or run.catalog.manifest['source_sha256'].get(script)!=script_sha
     or npc.get('dynamic') or npc['template']!=template or npc.get('source_index')!=source_index
     or npc.get('start_point')!=point or any(not math.isfinite(v) or abs(v)>1e7 for v in report['xyz'])):return []
 from els_server.game_data import client_data
 native=client_data().npc(template)
 if native['class_id']!=0 or native['script']!=script or native['is_npc'] is not True:return []
 source=dict(template=template,source_index=source_index,points=[point],active=True,gage=True,ally=False,
             team=1,no_drop=False,right=False,boss=False,boss_lines=1,key_code=-1,source_key_code=-1,rate=100,offset=[0,0,0])
 declared=run.graph['stages'][str(run.stage)]['parts'][str(run.part)]['groups']
 rows=[row for group in declared for row in group['npcs'] if row.get('source_index')==source_index]
 if rows!=[source] or any(npc.get(k)!=v for k,v in source.items() if k!='active'):return []
 from els_server.domain.formal_npc_hp import initialized_maximum
 hp=initialized_maximum(run,source)
 if npc['hp']!=hp or report['hp_bits']!=struct.unpack('>I',struct.pack('>f',hp))[0]:return []
 previous=run.defeated.get(npc['key'])
 if previous is not None:return [death_ack()] if previous==event.payload and npc['active'] is False else []
 if npc['active'] is not True:return []
 shadow=copy.copy(s);shadow.dungeon_run=copy.copy(run);shadow.dungeon_clock=copy.copy(s.dungeon_clock)
 shadow.dungeon_run.defeated={**run.defeated,npc['key']:bytes(event.payload)}
 replies=[death_ack(),empty_reward_death_notice(npc['key'],report['killer'])]+periodic(shadow)
 from els_server.protocol.protocol_codec import encode_event
 for reply in replies:encode_event(reply)
 for name in ('defeated','next','ready_at'):setattr(run,name,getattr(shadow.dungeon_run,name))
 npc['active']=False;s.defeated_npcs=run.defeated;s.part_end_notified=shadow.part_end_notified
 s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started
 return replies

def finish_death(s,event,npc,d,expired,notice):
 run=s.dungeon_run
 run.defeated[npc['key']]=bytes(event.payload);s.defeated_npcs=run.defeated
 if expired:npc['active']=False
 reply=[death_ack(),notice]
 if run.identity==38300 and npc['template']==1368:return reply+failed(s)
 from els_server.domain.raid_economy_flow import managed as raid_managed
 from els_server.domain.secret_clear_rewards import managed as secret_managed
 if not raid_managed(s) and not secret_managed(run) and s.drop_probe and npc['active'] and not npc['no_drop'] and not npc.get('ally') and npc.get('team',1)!=0:
  from els_server.domain.dungeon_drops import ground_drop_notice
  rule=local_rewards();amount=__import__('els_server.domain.formal_pve_economy',fromlist=['coin']).coin(run.identity,npc['boss'],rule['boss_ed'] if npc['boss'] else rule['ordinary_ed'])
  from els_server.domain.gm_rates import allow_drop
  if amount and allow_drop(s.reward_run_id,run.identity,(run.stage,run.part),npc['key'],npc['boss']):
   key=s.world_drop_sequence;s.world_drop_sequence+=1;xyz=d['xyz'][3:];template=coin_template(amount)
   notice=ground_drop_notice(key,xyz,uid=s.account.uid,template=template)
   s.world_drop_issued=dict(run_id=s.reward_run_id,stage=run.stage,part=run.part,npc_key=npc['key'],drop_id=key,
      owner=s.account.uid,template=template,ed=amount,quantity=0,xyz=list(xyz),
      payload_hex=notice.payload.hex(),death_proof_sha256=hashlib.sha256(event.payload).hexdigest(),pickup_committed=False)
   s.world_drops[key]=dict(s.world_drop_issued);reply.append(notice)
 return reply+periodic(s)


def clear(s):
 from els_server.domain.secret_clear_rewards import settle as secret_clear
 secret_reply=secret_clear(s)
 if secret_reply is not None:return secret_reply
 run=s.dungeon_run;rule=local_rewards()
 challenge_plan=getattr(s,'_challenge_repeat_plan',None)
 if challenge_plan is not None:
  if (challenge_plan[0]is not getattr(s,'reward_transaction',None)or not challenge_plan[0].in_transaction
      or s.active_challenge is None or not s.item_test):raise ValueError('Challenge repeat items require shared clear writer')
  rule=dict(rule,items=[*rule['items'],*challenge_plan[1]])
 challenge_source=None
 if challenge_plan is not None:
  from els_server.domain.challenge_repeat_rewards import source as challenge_reward_source
  challenge_source=challenge_reward_source(s,rule['items'],challenge_plan[3])
 raid_supply=getattr(s,'_raid_supply',None)
 if raid_supply is not None:
  if (raid_supply['owner'] is not s or raid_supply['transaction'] is not getattr(s,'reward_transaction',None)
      or not raid_supply['transaction'].in_transaction or not getattr(s,'_raid_phase_internal',False)):
   raise ValueError('Raid clear requires original phase writer')
  rule=dict(rule,clear_ed=0,clear_experience=raid_supply['experience'],items=raid_supply['plan'])
 from els_server.domain.legacy_pve_exp import clear_amount,experience_limit
 compat_clear=raid_supply['experience'] if raid_supply is not None else clear_amount(s)
 if compat_clear is not None:rule=dict(rule,clear_experience=compat_clear)
 from els_server.domain.gm_rates import clear_experience
 # Compatibility K already contains the run's pinned GM multiplier. Its
 # 30% clear increment must not receive that multiplier a second time.
 if compat_clear is None:rule=dict(rule,clear_experience=clear_experience(s,rule['clear_experience']))
 if getattr(s,'challenge_deadline',None) is not None and time.time()>=s.challenge_deadline:return failed(s)
 from els_server.domain.silver_mirror_flow import clear_rewards as mirror_clear
 mirror_reply=mirror_clear(s,rule)
 if mirror_reply is not None:return mirror_reply
 from els_server.domain.dungeon_equipment_loot_flow import clear_rewards
 loot_reply=clear_rewards(s,rule)
 if loot_reply is not None:return loot_reply
 if not s.reward_test:
  from els_server.domain.dungeon_clear import prototype_clear_notice
  reply=[prototype_clear_notice(s.reward_probe,map_id=run.identity)]
 else:
  from els_server.domain.dungeon_clear import reward_clear_notice,clear_identity_payload
  from els_server.protocol.local_messages import client_economy_fields
  elapsed=s.dungeon_clock.seconds()
  from els_server.domain.local_artifact_rules import assess_run,clear_base
  assessment=assess_run(run,elapsed)
  deaths=hashlib.sha256()
  for key,value in sorted(run.defeated.items()):deaths.update(struct.pack('>iI',key,len(value))+value)
  proof=(b'local-static-clear-v2'+struct.pack('>Qiii',s.account.uid,run.identity,run.stage,run.part)
         +bytes.fromhex(run.graph['source_sha256'])+deaths.digest())
  def encode(balances,best,economy):
   client_economy_fields(balances)
   return reward_clear_notice(result_ed(s,economy['ed'],transaction=getattr(s,'reward_transaction',None)),economy['experience'],s.account.uid,elapsed_seconds=elapsed,best_seconds=best,map_id=run.identity).payload
  if getattr(s,'active_challenge',None) is not None and s.challenge_clear_effect is None:
   s.challenge_clear_effect={**s.active_challenge,'now':challenge_plan[4]if challenge_plan is not None else int(time.time())}
  original=raid_supply['original_session']if raid_supply is not None else challenge_plan[2]if challenge_plan is not None else getattr(s,'_giant_task_actor',s)
  from els_server.domain.giant_daily_tasks import prepare as prepare_giant_task
  giant_task=prepare_giant_task(s)
  receipt=s.account.reward_store.grant(s.reward_run_id,proof,rule['clear_ed'],rule['clear_experience'],encode,
      item_plan=(rule['items'] or None) if s.item_test else None,dungeon_clear=(run.identity,elapsed),challenge_clear=getattr(s,'challenge_clear_effect',None),transaction=getattr(s,'reward_transaction',None),clear_assessment=assessment,artifact_base=clear_base(run.identity),title_economy='clear',attendance_clear=s.activity2026_awards.prepare_clear(original) if getattr(s,'activity2026_awards',None) is not None else None,experience_limit=experience_limit() if compat_clear is not None else None,resonance_source='clear' if compat_clear is not None else None,raid_reward_source=raid_supply['source'] if raid_supply is not None else challenge_source,daily_special=raid_supply.get('daily_special') if raid_supply is not None else __import__('els_server.domain.ariel_daily_special',fromlist=['prepare']).prepare(s),random_mission=raid_supply.get('random_mission')if raid_supply is not None else None,giant_task=giant_task,dungeon_result=prepare_result_clear(original))
  s.reward_receipt={'run_id':s.reward_run_id,**receipt};reply=[]
  if getattr(s,'reward_transaction',None) is None:
   from els_server.domain.gameplay_announcements import publish
   notices=list(receipt.get('announcements',()))
   if run.identity==38100 and run.henir_mode==2 and not receipt['replayed']:
    from els_server.protocol.native_notice_messages import achievement
    notices.append(achievement(6,s.account.character_identity()['name']))
   publish(s,notices)
  if s.item_test and receipt.get('items') and not s.clear_items_synced:
   from els_server.domain.dungeon_drops import pickup_inventory_notice
   ids={i['uid'] for i in receipt['items']};items=receipt['items'] if getattr(s,'reward_transaction',None) is not None else [i for i in s.account.get_inventory_snapshot()['items'] if i['uid'] in ids]
   reply.append(pickup_inventory_notice(items));s.clear_items_synced=True
  # The caller may own a shared group transaction. Read its receipt instead
  # of opening another connection before the group's commit is visible.
  committed=receipt.get('local_rules')
  if committed:
   a=committed['assessment'];reply.append(Event(0x201,kind=0x66b,payload=struct.pack('>ii',a['rank'],a['score'])))
  reply.append(Event(0x201,kind=0xc1,payload=clear_identity_payload(receipt['response'],run.identity)))
  if 'ariel_daily_status'in receipt:reply.append(receipt['ariel_daily_status'])
  if 'giant_task_notice'in receipt:reply.append(receipt['giant_task_notice'])
  if getattr(s,'active_challenge',None) is not None and getattr(s,'reward_transaction',None) is None:
   from els_server.domain.challenge_flow import notification
   reply.append(notification(s))
 s.clear_notified=True
 return reply

def failed(s):
 if s.clear_notified:return []
 from els_server.domain.dungeon_clear import failed_clear_notice
 s.clear_notified=True;s.dungeon_failed=True;s.reward_receipt=None;s.dungeon_clock.pause()
 reply=[failed_clear_notice(s.account.uid,s.dungeon_clock.seconds(),map_id=getattr(s.dungeon_run,'identity',None))]
 if getattr(s,'active_challenge',None) is not None:
  from els_server.domain.challenge_flow import notification
  reply.append(notification(s))
 return reply
