"""Atomic original native phase settlement; native combat/UI remain the client."""
import copy,hashlib,json,sqlite3,struct,time,uuid
from contextlib import closing
from pathlib import Path
from els_server.domain import formal_raid_economy as rules
from els_server.storage import raid_economy_state as state

def managed(s):return rules.definition(getattr(getattr(s,'dungeon_run',None),'identity',None))is not None

def application(s):
 return getattr(s,'application',None)or getattr(s,'_c1_local_application',None)

def _binding(members,room):
 from els_server.domain.dungeon_hp_c1 import _lease as current_lease
 from els_server.domain.friends_spawns import _checked_static_generation
 app=application(members[0])
 if app is None:raise ValueError('Raid actual Application is unavailable')
 dispatcher=app.world.dungeons
 paths=set();values=[];uids=frozenset(m.account.uid for m in members)
 if room is not None:
  if (tuple(room.members)!=members or room.phase!='part_end' or not room.party.get('raid_party')
      or room.party.get('run')is not room or tuple(room.party['members'])!=members
      or room.party.get('challenge')or room.party.get('challenge_pending')or room.party.get('solo_challenge')):raise ValueError('Raid original room barrier')
  generation=_checked_static_generation(dispatcher,room)
 else:
  if len(members)!=1 or dispatcher.room(members[0])is not None:raise ValueError('Raid original solo binding')
  generation=None
 for s in members:
  r=s.dungeon_run;d=rules.check_run(r)
  if (d is None or application(s) is not app or s.role!='game' or s.client_build!='dx11_260923'
      or not current_lease(s)or (app.config.mode=='friends'and not app.registry.enabled(s.account.account_id))
      or s.phase!='dungeon_active' or not s.dungeon_substage_synced or not s.part_end_notified
      or s.clear_notified or getattr(s,'dungeon_failed',False)or s.gate_stage_loading
      or not s.reward_test or not s.item_test or not s.drop_probe
      or getattr(s,'reward_transaction',None)is not None or s.account.characters is None
      or getattr(s,'active_challenge',None)is not None or getattr(s,'challenge_deadline',None)is not None
      or not isinstance(r.next,dict)or r.next.get('kind')not in(1,2,3,4)
      or r.ready_at is None or r.clock()<r.ready_at or getattr(s,'coop_error',None)or getattr(s,'social_overflow',False)
      or s.account.store.uid!=s.account.uid or s.account.reward_store.uid!=s.account.uid
      or getattr(s,'dungeon_participants',frozenset((s.account.uid,)))!=uids):raise ValueError('Raid current phase actor unavailable')
  if room is None:
   if r.run_id!=s.reward_run_id or s in app.world.party_of or s in app.world.members:raise ValueError('Raid original solo epoch')
  elif (dispatcher.room(s)is not room or app.world.party_of.get(s)is not room.party or s in app.world.members
        or r.run_id!=room.seed or s.reward_run_id!=str(uuid.uuid5(uuid.UUID(room.seed),'reward:'+str(s.account.uid)))):raise ValueError('Raid original member epoch')
  for p in(s.account.store.path,s.account.characters.path,s.account.reward_store.path,app.config.state_file):paths.add(Path(p).resolve())
  life=getattr(s,'known_resurrection_life',None)
  values.append((s,s.account,s.account.store,s.account.reward_store,r,s.shop_session_id,s.account.uid,s.account.account_id,
   s.reward_run_id,r.identity,r.run_id,r.stage,r.part,r.visits,r.graph['source_sha256'],json.dumps(r.next,sort_keys=True),r.ready_at,
   tuple(sorted(r.defeated.items())),None if life is None else (life.get('epoch'),life.get('number'),life.get('phase')),
   json.dumps(getattr(s,'_raid_life_witness',None),sort_keys=True)))
 if len(paths)!=1 or len(uids)!=len(members):raise ValueError('Raid original database/roster differs')
 return tuple(values),generation,next(iter(paths))

def _guard(members,room,binding,db):
 from els_server.storage.item_actor import require_active_character
 from els_server.storage.bank_state import account_for
 if _binding(members,room)!=binding:raise ValueError('Raid phase identity changed')
 main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
 if (not db.in_transaction or len(main)!=1 or Path(main[0][2]).resolve()!=binding[2]
     or any(r[1]not in('main','temp')for r in db.execute('PRAGMA database_list'))
     or db.execute('PRAGMA foreign_keys').fetchone()!=(1,)):raise ValueError('Raid original writer changed')
 for s in members:
  require_active_character(db,s.account.uid)
  if account_for(db,s.account.uid)!=s.account.account_id:raise ValueError('Raid saved owner changed')
 return True

def _context(s):
 r=s.dungeon_run;d=rules.check_run(r);life=getattr(s,'known_resurrection_life',None)
 if life is not None and life.get('epoch')==r.run_id:alive=life['phase']=='alive'
 else:alive=True # original fresh fully-loaded run
 witness=getattr(s,'_raid_life_witness',None)
 if witness is not None and witness['epoch']==r.run_id:alive=witness['phase']=='alive'
 from els_server.domain.legacy_pve_exp import policy
 bp=r.formal_raid_experience_bp
 base=policy()['levels'][str(d['npc_level'])]
 amount=min(2**31-1,base*rules.policy()['local']['phase_experience_level_multiplier']*bp//10000)
 proof=hashlib.sha256()
 # Include every accepted original retirement in this native phase's run;
 # source instance and previously completed phases remain in the SQL source.
 for k,v in sorted(r.defeated.items()):proof.update(struct.pack('>iI',k,len(v))+v)
 return dict(owner=s.account.uid,run=s.reward_run_id,source_run=r.run_id,dungeon=r.identity,stage=r.stage,part=r.part,visits=r.visits,
  graph_sha256=r.graph['source_sha256'],proof=proof.hexdigest(),alive=alive,phase_experience=amount,experience_bp=bp)

_ADOPT=('previous_dungeon_part','gate_stage','part_end_notified','defeated_npcs','summon_keys','summon_deaths','summon_requests','summon_next_key',
 'dungeon_substage_synced','gate_stage_loading','clear_notified','reward_receipt','clear_items_synced','challenge_clear_effect','_quest_seen_events','_artifact_view')

def _clear_observers(db,s,shadow,before,replies,guard,members):
 # Reuse the original quest, pet and Artifact consumers on this exact writer.
 # Shared-room request handling bypasses LocalSession.handle's observers.
 from els_server.domain.quest_flow import store as quest_store
 from els_server.storage.seal_quests import load_character
 r=s.dungeon_run;level=getattr(s,'_quest_run_levels',{}).get(r.run_id,before['level'])
 assessment=shadow.reward_receipt.get('local_rules')
 event=dict(kind='clear',dungeon=r.identity,level=level,rank=assessment['assessment']['rank']if assessment else None)
 proof=(r.run_id+':'+r.graph['source_sha256']).encode()
 replies+=quest_store(s).record(r.run_id+':clear',event,proof,transaction=db,validate=guard)
 from els_server.domain.weapon_growth_flow import settled as growth_settled
 replies+=growth_settled(s,shadow,db,members,guard)
 shadow._quest_seen_events=set(getattr(s,'_quest_seen_events',set()))|{r.run_id+':clear'}
 from els_server.storage.pet_progression import active as active_pet
 from els_server.protocol.pet_progression_messages import progress as pet_notice
 try:pet=active_pet(db,s.account.uid)
 except ValueError:pet=None
 if pet is not None:replies.append(pet_notice(s.account.uid,pet))
 current=load_character(db,s.account.uid,s.account.account_id);artifact=current.get('artifact')
 if artifact and artifact!=before.get('artifact'):
  from els_server.protocol.artifact_messages import notice
  replies.append(notice(current,artifact['evolution']!=before['artifact']['evolution']))
  shadow._artifact_view=((str(s.account.store.path),s.account.uid),(artifact['evolution'],artifact['level'],artifact['experience'],tuple(artifact['potentials'])))

class _ShadowHP:
 """Prepare new-stage bytes through the original owned C1 HP consumer.

 C1 keeps its exact original run/session identity and all its existing lease,
 source fingerprint and explicit-HP checks. This temporary shadow only asks
 that consumer for the next declared source actors; no active actor HP changes.
 The original context is retained on the original run at the commit handoff.
 """
 def __init__(self,original,shadow):self.original=original;self.shadow=shadow
 def check(self,run,*,emitting=False):
  if (run is not self.shadow or run.identity!=self.original.identity or run.run_id!=self.original.run_id
      or run.graph is not self.original.graph or run.catalog is not self.original.catalog):raise ValueError('Raid private HP preparation identity')
  self.original.hp_context.check(self.original,emitting=emitting)
 def source_hp(self,run,stage,part,group,source,fallback):
  self.check(run)
  return self.original.hp_context.source_hp(self.original,stage,part,group,source,fallback)

def settle(members,event,room=None):
 from els_server.domain import dungeon_flow
 from els_server.domain.raid_reward_items import _issue_source
 from els_server.domain.dungeon_drops import pickup_inventory_notice
 from els_server.protocol.protocol_codec import encode_event
 from els_server.protocol.raid_economy_protocol import weapon_point,point_snapshot
 members=tuple(members);bound=_binding(members,room)
 if (event.event_id!=0x202 or event.kind!=0xbb or event.performers not in((),(0,))or event.payload_mode!=0
     or event.uid!=2**64-1 or event.target_uid!=2**64-1
     or any(event.payload!=struct.pack('>b',s.dungeon_run.part)for s in members)):raise ValueError('Raid original phase completion request')
 shadows=[];deliveries=[]
 with closing(sqlite3.connect(bound[2],timeout=10))as db,db:
  db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');guard=lambda writer:_guard(members,room,bound,writer)
  now=int(time.time())
  prepared=state.prepare_batch(db,[_context(s)for s in members],now,guard)
  for s,result in zip(members,prepared):
   from els_server.storage.seal_quests import load_character
   character_before=load_character(db,s.account.uid,s.account.account_id)
   shadow=copy.copy(s);shadow.dungeon_run=copy.copy(s.dungeon_run);shadow.dungeon_clock=copy.copy(s.dungeon_clock)
   for name,value in s.dungeon_run.__dict__.items():
    if name not in('catalog','graph','clock','hp_context'):setattr(shadow.dungeon_run,name,copy.deepcopy(value))
   if s.dungeon_run.hp_context is not None:shadow.dungeon_run.hp_context=_ShadowHP(s.dungeon_run,shadow.dungeon_run)
   shadow.reward_transaction=db;shadow._raid_phase_internal=True
   r=s.dungeon_run;final=r.next['kind']==4;operation=s.reward_run_id if final else str(uuid.uuid5(uuid.UUID(s.reward_run_id),'raid-native-phase:'+str(r.stage)))
   cap=_issue_source(db,s.account.uid,operation,'phase',result['source'],result['items'],guard)if result['items']else None
   shadow._raid_supply=dict(owner=shadow,original_session=s,transaction=db,plan=result['items'],source=cap,
    experience=state.run_experience(db,s.account.uid,s.reward_run_id,r.identity)if final else 0)
   replies=[]
   if not final:
    proof=b'formal-raid-phase-v1\0'+state.canonical(result['source']).encode()
    receipt=s.account.reward_store.grant(operation,proof,0,0,lambda b:b'raid-phase-v1',item_plan=result['items']or None,transaction=db,raid_reward_source=cap)
    if receipt.get('items'):replies.append(pickup_inventory_notice(receipt['items']))
   replies+=dungeon_flow.handle(shadow,event)
   if final:_clear_observers(db,s,shadow,character_before,replies,guard,members)
   f=rules.definition(r.identity)['family']
   if f in('rosso','berthe','abyss','barkat'):replies.append(weapon_point(rules.adjust(f)['Index'],state.progress(db,s.account.uid,f)[0]))
   replies.append(point_snapshot([(n,state.progress(db,s.account.uid,'accessory:'+str(n))[0],t)for n,t in((1,136175),(2,136179),(3,30876))],db=db,owner=s.account.uid))
   from els_server.domain.raid_reward_flow import weekly_events
   replies+=weekly_events(db,s.account.uid,now)
   for reply in replies:encode_event(reply)
   shadows.append(shadow);deliveries.append((s,replies))
  # Prepare complete mailbox replacements before the economic commit. No send,
  # serialization, inventory read or callback is allowed in the commit handoff.
  prepared_boxes=[]
  if room is not None:
   from collections import deque
   from els_server.domain.friends_world import Mailbox
   for s,replies in deliveries:
    box=s.mailbox
    if type(box)is not Mailbox:raise ValueError('Raid peer mailbox type')
    clone=Mailbox();clone.messages=deque(box.messages);clone.moves=dict(box.moves);clone.bytes=box.bytes
    snapshot=(box,box.bytes,tuple(box.messages),tuple(box.moves.items()))
    for reply in replies:
     if reply.kind!=0xbc:clone.append(reply)
    prepared_boxes.append((s,clone,snapshot))
  guard(db)
  for s,clone,before in prepared_boxes:
   box=s.mailbox
   if (box,box.bytes,tuple(box.messages),tuple(box.moves.items()))!=before:raise ValueError('Raid peer mailbox changed')
 for s,shadow in zip(members,shadows):
  original=s.dungeon_run;hp_context=original.hp_context;original.__dict__.clear();original.__dict__.update(shadow.dungeon_run.__dict__);original.hp_context=hp_context
  for name in _ADOPT:
   if hasattr(shadow,name):setattr(s,name,getattr(shadow,name))
  s.defeated_npcs=original.defeated
  s.dungeon_clock.total=shadow.dungeon_clock.total;s.dungeon_clock.started=shadow.dungeon_clock.started
 for s,clone,before in prepared_boxes:s.mailbox=clone
 return deliveries

def solo(s,event):
 if not managed(s)or event.kind!=0xbb or getattr(s,'_raid_phase_internal',False):return None
 r=s.dungeon_run
 if not isinstance(r.next,dict)or r.next.get('kind')==0:return None
 # Shared rooms invoke the one roster writer from FriendsDungeons.end_part.
 app=application(s)
 if app is None:return []
 if app.world.dungeons.room(s)is not None:return []
 if s.clear_notified:return None
 try:return settle((s,),event)[0][1]
 except (ValueError,sqlite3.Error,OverflowError,struct.error):return []
