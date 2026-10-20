"""Native solo lifecycle for source-driven static dungeon routes.
Unverified scripted encounters are rejected at admission, never auto-cleared.
"""
import functools,hashlib,json,math,struct,time
from els_server.paths import PROJECT_ROOT
from els_server.protocol.protocol_codec import Event
from els_server.domain.dungeon_lifecycle import death_report,death_ack,empty_reward_death_notice,part_end_notice
from els_server.domain.reward_rules import item_plan

@functools.lru_cache(maxsize=1)
def local_rewards():
 r=json.loads((PROJECT_ROOT/'config/dungeon_local_rules.json').read_text(encoding='utf8'))
 if r['schema_version']!=1 or r['provenance']!='local_policy':raise ValueError('Dungeon local reward provenance')
 if any(type(r[k]) is not int or not 0<=r[k]<=2**31-1 for k in ('clear_ed','clear_experience','ordinary_ed','boss_ed')):raise ValueError('Local dungeon reward bound')
 if r['coin_template']!=127000:raise ValueError('Unverified local coin')
 return {**r,'items':[item_plan(**i) for i in r['clear_items']]}

def periodic(session):
 s=session
 if (s.dungeon_run is not None and s.phase=='dungeon_active' and not s.clear_notified
     and getattr(s,'challenge_deadline',None) is not None and time.time()>=s.challenge_deadline):return failed(s)
 if (s.dungeon_run is None or s.phase!='dungeon_active' or not s.dungeon_substage_synced
     or s.part_end_notified or s.clear_notified):return []
 if getattr(s.dungeon_run,'memory1_quest_barrier',frozenset())-set(s.dungeon_run.defeated):return []
 if s.dungeon_run.poll_ready():
  s.part_end_notified=True;s.dungeon_clock.pause()
  return [part_end_notice(s.dungeon_run.part)]
 return []

def handle(s,event):
 run=s.dungeon_run
 if run is None or s.phase!='dungeon_active' or event.event_id!=0x202:return None
 if event.kind==0xb8:
  # Current 1044A10 -> 1117280 -> 3B6DA30 writes one part byte.
  # B9 -> Game v600=1044B20 consumes an i32 result, removes its wait.
  # BB/BC can advance the native part before its queued B8 is emitted.
  # 1044A25 reads the part at send time, so either end of the last proven
  # transition may be reported. Acknowledging it must not open the new gate.
  transition=run.completed_transition
  late=(transition is not None and (run.stage,run.part,run.visits)==transition['target']
        and event.payload in transition['parts'])
  valid=(s.dungeon_substage_synced and not s.clear_notified and
         event.payload==struct.pack('>b',run.part) and
         all(n['key'] in run.defeated for n in run.current['npcs'] if n['active'] and n.get('team',1)!=0))
  if valid:run.portal_requested=True
  elif late:return [Event(0x201,kind=0xb9,payload=bytes(4))]
  return [Event(0x201,kind=0xb9,payload=struct.pack('>i',0 if valid else -1))]+(periodic(s) if valid else [])
 if event.kind==0xad:
  try:d=death_report(event.payload)
  except ValueError:return []
  # Finite static-controller adapters must not consume an already admitted
  # dynamic actor's original expiry. Retain the existing expiry decoder and
  # exact server-allocated identity; zero is never an alias for another actor.
  actor=next((n for n in run.current['npcs'] if n['key']==d['index']),None)
  from els_server.domain.summons import valid_sentry_death
  dynamic_expiry=actor is not None and actor.get('dynamic') and valid_sentry_death(d,s.account.uid)
  if dynamic_expiry:
   from els_server.domain.dungeon_equipment_loot_flow import current_lease
   if (event.performers!=(0,) or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
       or s.role!='game' or not current_lease(s) or s.clear_notified
       or getattr(s,'reward_transaction',None) is not None or getattr(s,'reward_run_id',None)!=run.run_id
       or frozenset(getattr(s,'dungeon_participants',(s.account.uid,)))!=frozenset((s.account.uid,))):return []
  else:
   from els_server.domain.lithia_memory1_retirements import handle as memory1_retirement
   retired=memory1_retirement(s,event,d)
   if retired is not None:return retired
   from els_server.domain.story_controller_retirements import handle as story_retirement
   retired=story_retirement(s,event,d)
   if retired is not None:return retired
  if d['index'] in s.summon_keys:return None
  npc=next((n for n in run.current['npcs'] if n['key']==d['index']),None)
  hp=struct.unpack('>f',struct.pack('>I',d['hp_bits']))[0]
  participants=getattr(s,'dungeon_participants',frozenset((s.account.uid,)))
  # Inactive script controllers can report their own destruction without a
  # player killer. They still require a declared current actor and a native
  # death payload; hostile combat actors retain participant-only identity.
  scripted=npc is not None and not npc['active'] and (npc['no_drop'] or npc.get('ally'))
  from els_server.domain.summons import valid_sentry_death
  expired=npc is not None and npc.get('dynamic') and valid_sentry_death(d,s.account.uid)
  identities=participants|frozenset((0,2**64-1)) if scripted or expired else participants
  if (npc is None or not s.dungeon_substage_synced or event.performers!=(0,) or d['flag'] not in (0,1) and not expired
      or any(d[name] not in identities for name in ('source','killer','last_uid'))
      or any(uid not in participants for name in ('contribution','readiness','counters') for uid in d[name])
      or not math.isfinite(hp) or hp<=0 and not expired):return []
  # Native scripts can set an actor's maximum HP after initialization. The
  # local single-player prototype trusts authenticated death reports; it does
  # not claim authoritative damage simulation from a matching max-HP scalar.
  previous=run.defeated.get(npc['key'])
  if previous is not None:return [death_ack()] if previous==event.payload else []
  if s.clear_notified:return []
  from els_server.domain.dungeon_equipment_loot_flow import accepted_death
  loot_reply=accepted_death(s,event,npc,d,expired)
  if loot_reply is not None:return loot_reply
  from els_server.domain.legacy_pve_exp import accepted_death as experience_death
  xp_reply=experience_death(s,event,npc,d,expired,finish_death)
  if xp_reply is not None:return xp_reply
  return finish_death(s,event,npc,d,expired,empty_reward_death_notice(npc['key'],d['killer']))
 if event.kind==0xb3:
  if len(event.payload)!=9 or event.payload[:5]!=bytes(5):return []
  value=struct.unpack_from('>f',event.payload,5)[0]
  if not math.isfinite(value) or not 0<=value<=1e9:return []
  reply=[Event(0x201,kind=0xb4,payload=bytes(4)),Event(0x201,kind=0xb5,payload=struct.pack('>iQ',0,s.account.uid))]
  if not s.dungeon_substage_synced:
   from els_server.protocol.dungeon_messages import initial_part,begin_substage
   reply.extend([Event(0x201,kind=0xb6,payload=bytes(16)),initial_part(run.part),begin_substage(run.part,npc_entries=((n['key'],n['template']) for n in run.current['npcs']))])
   s.dungeon_substage_synced=True;s.gate_stage_loading=False;s.dungeon_clock.resume();run.loaded()
  return reply+periodic(s)
 if event.kind==0xbb:
  if len(event.payload)!=1:return []
  part=struct.unpack('>b',event.payload)[0]
  if part!=run.part or s.gate_stage_loading:
   return [Event(0x201,kind=0xbc,payload=bytes(4))] if part==getattr(s,'previous_dungeon_part',None) else []
  if not s.part_end_notified:return []
  reply=[Event(0x201,kind=0xbc,payload=bytes(4))]
  if s.clear_notified:return reply
  if not run.poll_ready():return []
  source=(run.stage,run.part,run.visits)
  target=run.next
  if target['kind']==4:
   run.completed_transition=dict(target=source,parts=(struct.pack('>b',run.part),))
   reply.extend(clear(s));return reply
  # Prepare the stage before committing the cursor so encoding failure does
  # not discard the completed part; the fixed run seed preserves retry bytes.
  s.previous_dungeon_part=run.part;transition=run.advance();s.gate_stage=run.stage
  run.completed_transition=dict(target=(run.stage,run.part,run.visits),parts=tuple({struct.pack('>b',source[1]),struct.pack('>b',run.part)}))
  s.part_end_notified=False;s.defeated_npcs=run.defeated
  if transition=='stage':
   s.summon_keys=set();s.summon_deaths={};s.summon_requests={};s.summon_next_key=16
   s.dungeon_substage_synced=False;s.gate_stage_loading=True
   reply.append(run.population_event())
  else:
   from els_server.protocol.dungeon_messages import initial_part,begin_substage
   reply.extend([initial_part(run.part),begin_substage(run.part,npc_entries=((n['key'],n['template']) for n in run.current['npcs']))])
   s.dungeon_clock.resume();run.loaded()
  return reply+periodic(s)
 return None

def finish_death(s,event,npc,d,expired,notice):
 run=s.dungeon_run
 run.defeated[npc['key']]=bytes(event.payload);s.defeated_npcs=run.defeated
 if expired:npc['active']=False
 reply=[death_ack(),notice]
 if run.identity==38300 and npc['template']==1368:return reply+failed(s)
 if s.drop_probe and npc['active'] and not npc['no_drop'] and not npc.get('ally') and npc.get('team',1)!=0:
  from els_server.domain.dungeon_drops import ground_drop_notice
  rule=local_rewards();amount=rule['boss_ed'] if npc['boss'] else rule['ordinary_ed']
  from els_server.domain.gm_rates import allow_drop
  if amount and allow_drop(s.reward_run_id,run.identity,(run.stage,run.part),npc['key'],npc['boss']):
   key=s.world_drop_sequence;s.world_drop_sequence+=1;xyz=d['xyz'][3:]
   notice=ground_drop_notice(key,xyz,uid=s.account.uid,template=rule['coin_template'])
   s.world_drop_issued=dict(run_id=s.reward_run_id,stage=run.stage,part=run.part,npc_key=npc['key'],drop_id=key,
      owner=s.account.uid,template=rule['coin_template'],ed=amount,quantity=0,xyz=list(xyz),
      payload_hex=notice.payload.hex(),death_proof_sha256=hashlib.sha256(event.payload).hexdigest(),pickup_committed=False)
   s.world_drops[key]=dict(s.world_drop_issued);reply.append(notice)
 return reply+periodic(s)


def clear(s):
 run=s.dungeon_run;rule=local_rewards()
 from els_server.domain.legacy_pve_exp import clear_amount,experience_limit
 compat_clear=clear_amount(s)
 if compat_clear is not None:rule=dict(rule,clear_experience=compat_clear)
 from els_server.domain.gm_rates import clear_experience
 # Compatibility K already contains the run's pinned GM multiplier. Its
 # 30% clear increment must not receive that multiplier a second time.
 if compat_clear is None:rule=dict(rule,clear_experience=clear_experience(s,rule['clear_experience']))
 if getattr(s,'challenge_deadline',None) is not None and time.time()>=s.challenge_deadline:return failed(s)
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
   return reward_clear_notice(economy['ed'],economy['experience'],s.account.uid,elapsed_seconds=elapsed,best_seconds=best,map_id=run.identity).payload
  if getattr(s,'active_challenge',None) is not None and s.challenge_clear_effect is None:
   s.challenge_clear_effect={**s.active_challenge,'now':int(time.time())}
  receipt=s.account.reward_store.grant(s.reward_run_id,proof,rule['clear_ed'],rule['clear_experience'],encode,
      item_plan=rule['items'] if s.item_test else None,dungeon_clear=(run.identity,elapsed),challenge_clear=getattr(s,'challenge_clear_effect',None),transaction=getattr(s,'reward_transaction',None),clear_assessment=assessment,artifact_base=clear_base(run.identity),title_economy='clear',attendance_clear=s.activity2026_awards.prepare_clear(s) if getattr(s,'activity2026_awards',None) is not None else None,experience_limit=experience_limit() if compat_clear is not None else None,resonance_source='clear' if compat_clear is not None else None)
  s.reward_receipt={'run_id':s.reward_run_id,**receipt};reply=[]
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
