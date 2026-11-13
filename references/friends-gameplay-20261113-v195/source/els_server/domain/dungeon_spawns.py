"""Current NPC-script 2CE queue; native Lua -> 1AAB5D0 -> 1AAD360 -> 1B21990.

Only verified templates reachable from the current stage's READY_NPC and
captured AI references are admitted. Player summons retain their own adapter.
"""
import hashlib,struct
from els_server.domain.summons import LAYOUTS,_decode_rows,summon_ack,PLAYER_SUMMON_TEMPLATES,player_summon_templates
from els_server.domain.dungeon_npcs import encode_npc
from els_server.domain.dungeon_routes import npc_initialization
from els_server.domain.combat_audit import dungeon_summon_observation
from els_server.protocol.protocol_codec import Event,encode_event

def occupied_slots(s):
 if s.dungeon_run is not None:npcs=s.dungeon_run.current['npcs'];dead=s.dungeon_run.defeated
 elif s.population_test:
  from els_server.domain.dungeon_population import population
  npcs=population(s.gate_stage)['npcs'];dead=s.defeated_npcs
 else:npcs=[dict(key=i) for i in range(3)];dead=s.defeated_npcs
 return sum(n['key'] not in dead for n in npcs)+len(s.summon_keys-set(s.summon_deaths))

class _QualificationError(ValueError):pass

def decode(payload,validate,*,parameters=False,diagnostic=None):
 def checked(dto,extra):
  if not parameters and extra:raise ValueError('Unsupported NPC extension')
  try:
   if parameters:validate(dto,extra)
   else:validate(dto)
  except ValueError as error:raise _QualificationError from error
 candidates={};failures={}
 for fields in LAYOUTS.values():
  try:
   rows=_decode_rows(payload,0,fields,(),validate=checked)
   identity=tuple((bytes(dto),tuple(sorted(extra.items())))for dto,extra in rows)
   candidates[identity]=rows
  except (ValueError,OverflowError,struct.error)as error:
   if diagnostic is not None:
    reason=('qualification'if isinstance(error,_QualificationError)else
        'location'if str(error)=='Invalid summon location'else
        'parameters'if str(error)=='Unsupported NPC extension'else'layout')
    failures[reason]=failures.get(reason,0)+1
 if diagnostic is not None:
  diagnostic.update(spawn_shape='decoded'if len(candidates)==1 else
      'ambiguous'if candidates else'unrecognized_or_unqualified',spawn_decode_failures=failures)
 if len(candidates)!=1:raise ValueError('Unrecognized or ambiguous NPC spawn mode')
 rows=next(iter(candidates.values()))
 return rows if parameters else[dto for dto,extra in rows]

def handle(s,event,sequence,*,owned_targets_only=False):
 if event.event_id!=0x202 or event.kind!=0x2ce or s.dungeon_run is None:return None
 run=s.dungeon_run
 if type(sequence) is not int or not 1<=sequence<2**32:return [summon_ack(-1)]
 request_key=(s.shop_session_id,sequence) if owned_targets_only else sequence
 digest=hashlib.sha256(event.payload).digest();old=run.dynamic_requests.get(request_key)
 if old is not None:return [summon_ack(0 if old==digest else -1)]
 if (s.phase!='dungeon_active' or not s.population_test or not s.dungeon_substage_synced or s.clear_notified
     or s.part_end_notified):return [summon_ack(-1)]
 allowed=set(run.graph['stages'][str(run.stage)]['allowed_summons'])
 if owned_targets_only:
  from els_server.domain.special_riding_targets import templates
  allowed=templates(run)
  if not allowed:return [summon_ack(-1)]
 owners={0,2**64-1,s.account.uid,*run.reserved_keys,*s.summon_keys}
 player_allowed=None
 def validate(dto,extra):
  nonlocal player_allowed
  key,template=struct.unpack_from('<ii',dto)
  creator=struct.unpack_from('<Q',dto,0x6d)[0]
  if owned_targets_only and (template not in allowed or creator!=s.account.uid):
   raise ValueError('Riding target is not owned by this participant')
  if template in PLAYER_SUMMON_TEMPLATES and creator==s.account.uid:
   if player_allowed is None:
    player_allowed=(player_summon_templates(s.account.character())
                    if s.client_build=='dx11_260923' and s.role=='game' else frozenset())
   if template not in player_allowed:raise ValueError('Player skill qualification')
   return
  if key!=-1 or template not in allowed:raise ValueError('NPC not declared by current encounter')
  if extra:raise ValueError('Unsupported scene NPC extension')
  if creator not in owners:raise ValueError('NPC creator outside current encounter')
  if any(dto[o] not in (0,1) for o in (0x4e,0x54,0x61,0x65,0x66)):raise ValueError('NPC flag bound')
 diagnostic={};s._spawn_diagnostic=(sequence,diagnostic)
 try:decoded=decode(event.payload,validate,parameters=True,diagnostic=diagnostic)
 except ValueError:return None  # Preserve the existing player-only decoder.
 rows=[dto for dto,extra in decoded]
 diagnostic.update(spawn_templates=[struct.unpack_from('<i',dto,4)[0]for dto in rows],
     spawn_templates_declared=all(struct.unpack_from('<i',dto,4)[0]in allowed for dto in rows),
     spawn_creator_in_current_scene=all(struct.unpack_from('<Q',dto,0x6d)[0]in owners for dto in rows))
 player_indexes={i for i,dto in enumerate(rows)if struct.unpack_from('<i',dto,4)[0]in PLAYER_SUMMON_TEMPLATES and struct.unpack_from('<Q',dto,0x6d)[0]==s.account.uid}
 if len(player_indexes)==len(rows):return None  # Keep the player-only lifecycle.
 # Source-bound compatibility for legacy Rose performance references in Ain.
 # Creating them starts a foreign scene after Ain's skill guide has run;
 # returning an error instead opens the client's empty error dialog. Complete
 # only these original inactive team0 requests as a no-op. No actors, guide,
 # clear state or rewards are fabricated; Ain's own source continues normally.
 if (run.identity==41420 and run.stage==0 and run.part==1
     and s.account.character()['unit_type']==12
     and run.graph['source_sha256']=='466d5205049ee4f7bf1d49a4a36b5ad847219e4b24531fe99681e2be99e06a46'
     and any(struct.unpack_from('<i',r,4)[0] in (2185,2186) for r in rows)):
  templates=[struct.unpack_from('<i',r,4)[0] for r in rows]
  original=(1<=len(rows)<=2 and len(set(templates))==len(rows)
      and all(t in (2185,2186) for t in templates)
      and all(r[8]==0 and r[0x4e]==0 and r[0x66]==0
          and struct.unpack_from('<fff',r,9)==(0.,0.,0.)
          and struct.unpack_from('<Q',r,0x6d)[0] in (0,2**64-1) for r in rows))
  if not original or len(run.dynamic_requests)>=4096:return [summon_ack(-1)]
  run.dynamic_requests[request_key]=digest
  return [summon_ack()]
 if len(run.dynamic_requests)>=4096:return [summon_ack(-1)]
 # The native scene has 80 concurrent slots, not 80 lifetime identities.
 # Retired records remain available for duplicate death acknowledgements.
 if occupied_slots(s)+len(rows)>80:return [summon_ack(-1)]
 try:free=run.new_npc_keys(len(rows),s.summon_keys|set(range(16))if player_indexes else s.summon_keys)
 except ValueError:return [summon_ack(-1)]
 entries=[];wires=[];initial=[];player_keys=set()
 for index,((dto,extra),key) in enumerate(zip(decoded,free)):
  struct.pack_into('<i',dto,0,key)
  if index in player_indexes:
   player_keys.add(key);wires.append(encode_npc(dto,0,extensions=extra));continue
  template=struct.unpack_from('<i',dto,4)[0];boss=bool(dto[0x61])
  from els_server.domain.formal_npc_hp import summoned_maximum
  hp,npc_level=summoned_maximum(run,template)
  # The incoming level is a native hint; the admitted source owns the level.
  dto[8]=npc_level
  from els_server.domain.formal_npc_hp import initialization_hp
  context=(run.identity,run.graph['source_sha256'],npc_level,run.stage)
  base_hp,hp=initialization_hp(run.catalog,hp,context)
  init=npc_initialization(run.catalog,template,base_hp,dynamic_context=context);wire=encode_npc(dto,0)
  entries.append(dict(key=key,template=template,key_code=struct.unpack_from('<i',dto,0x4f)[0],active=bool(dto[0x4e]),team=0 if dto[0x66] else 1,ally=bool(dto[0x66]),no_drop=True,boss=boss,hp=hp,dynamic=True,wire=wire,init=init))
  wires.append(wire);initial.append(struct.pack('>i',key)+init)
 # C50040: NPC vector, four-byte flags map, scalar, byte vector,
 # 2BDD300 -> 2C19E70's instance initialization map, then two maps.
 # Current original 1AADAA0 -> C50040 -> 1AEB790 consumes this byte
 # vector before native death lookup. Keep flags/scalar and init maps;
 # reuse the installed BD encoder, without client or combat changes.
 from els_server.protocol.npc_uid_map import uid_translation_vector
 uid_map=uid_translation_vector((e['key'],e['template']) for e in entries)
 packet=Event(0x201,kind=0x2d0,payload=struct.pack('>I',len(rows))+b''.join(wires)+bytes(8)+uid_map+struct.pack('>I',len(initial))+b''.join(initial)+bytes(8))
 # All decoding, bounds and serialization finish before changing the run.
 encode_event(packet)
 observation=dungeon_summon_observation(s,(struct.unpack_from('<i',rows[i],4)[0] for i in player_indexes),sequence)
 keys=s.summon_keys|player_keys
 requests=dict(s.summon_requests)
 if player_keys:requests[sequence]=event.payload
 run.current['npcs'].extend(entries);run.dynamic_requests[request_key]=digest
 if player_keys:
  s.summon_keys=keys;s.summon_requests=requests;s.summon_next_key=max(s.summon_next_key,max(player_keys)+1)
 if observation is not None:s._combat_summon_observation=observation
 return [summon_ack(),packet]
