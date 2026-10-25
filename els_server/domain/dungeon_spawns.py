"""Current NPC-script 2CE queue; native Lua -> 1AAB5D0 -> 1AAD360 -> 1B21990.

Only verified templates reachable from the current stage's READY_NPC and
captured AI references are admitted. Player sentries retain their own adapter.
"""
import functools,hashlib,math,re,struct
from els_server.domain.summons import LAYOUTS,summon_ack
from els_server.domain.dungeon_npcs import encode_npc
from els_server.domain.dungeon_routes import npc_initialization
from els_server.protocol.protocol_codec import Event

def occupied_slots(s):
 if s.dungeon_run is not None:npcs=s.dungeon_run.current['npcs'];dead=s.dungeon_run.defeated
 elif s.population_test:
  from els_server.domain.dungeon_population import population
  npcs=population(s.gate_stage)['npcs'];dead=s.defeated_npcs
 else:npcs=[dict(key=i) for i in range(3)];dead=s.defeated_npcs
 return sum(n['key'] not in dead for n in npcs)+len(s.summon_keys-set(s.summon_deaths))

def decode(payload,validate):
 if not isinstance(payload,bytes) or len(payload)<4:raise ValueError('NPC spawn vector')
 count=struct.unpack_from('>I',payload)[0]
 if not 1<=count<=64:raise ValueError('NPC spawn count')
 candidates={}
 for fields in LAYOUTS.values():
  try:
   position=4;rows=[]
   for _ in range(count):
    dto=bytearray(0xa4)
    for offset,size,xor,kind in fields:
     if position+size>len(payload):raise ValueError('Truncated NPC spawn')
     raw=payload[position:position+size];position+=size
     if kind=='empty':
      n=int.from_bytes(raw,'big')
      if offset is None:
       if n>64 or position+n>len(payload):raise ValueError('NPC padding bound')
       position+=n
      elif n:raise ValueError('Unsupported NPC extension')
     elif size==12:dto[offset:offset+size]=b''.join(raw[i:i+4][::-1] for i in (0,4,8))
     else:dto[offset:offset+size]=(int.from_bytes(raw,'big')^xor).to_bytes(size,'little')
    validate(dto);rows.append(dto)
   if position!=len(payload):raise ValueError('Trailing NPC spawn bytes')
   candidates[tuple(bytes(r) for r in rows)]=rows
  except (ValueError,OverflowError,struct.error):continue
 if len(candidates)!=1:raise ValueError('Unrecognized or ambiguous NPC spawn mode')
 return next(iter(candidates.values()))

# Lua-script scene objects. A dungeon cmd block creates these when the player
# interacts with the scene, so the stage's READY_NPC list - and therefore the
# pinned route graph - never carries them, and the native loader answers
# DUNGEON-side -1 while the client waits for an actor that never arrives.
#
# The family is derived from the route's own source file instead of a
# hand-listed id set, because a dungeon owns several such panels and the
# client asks for whichever one the player interacted with: 35250 creates
# all five mural panels (9305..9309), not only the first one recorded.
# A route sourced from Dungeon_<STEM>.lua owns every <STEM>_*.lua controller
# its graph does not already declare, and of those it may only create the two
# shapes this build proves are client-side scene requests:
#   - a numbered <STEM>..._PART<n>.lua panel (the interaction/scene markers), or
#   - a script the route's own pinned source manifest already lists.
# Prefix matching alone is not enough to be safe (EN_TUNNEL_* would admit 135
# combat-era objects), so the four guards below stay: dungeon-wide script
# family, client-side enum agreement, controller class, and absence from the
# static graph.
SCENE_CLASS=103
PART_PANEL=re.compile(r'^.*_PART\d+\.LUA$')

@functools.lru_cache(maxsize=8192)
def scene_controller(template):
 """True when the client build declares this template as a scene controller.

 Class 103 carries the Lua scene objects (doors, dummies, panels, triggers);
 the combat class carries real actors and never qualifies here.
 """
 if type(template) is not int:return False
 from els_server.game_data import client_data
 try:native=client_data().npc(template)
 except (ValueError,KeyError):return False
 script=native.get('script')
 return native.get('class_id')==SCENE_CLASS and isinstance(script,str) and script.endswith('.lua')

def scene_signature(run):
 source=run.graph.get('source')
 if not isinstance(source,str) or not source.lower().endswith('.lua'):return None
 stem=source.rsplit('/',1)[-1][:-4]
 if stem.lower().startswith('dungeon_'):stem=stem[8:]
 return stem.upper() or None

_DECLARED={}
def declared_templates(run):
 cached=_DECLARED.get(run.identity)
 if cached is not None:return cached
 found=set()
 def walk(value):
  if isinstance(value,dict):
   template=value.get('template')
   if type(template) is int:found.add(template)
   for child in value.values():walk(child)
  elif isinstance(value,list):
   for child in value:walk(child)
 walk(run.graph)
 _DECLARED[run.identity]=cached=frozenset(found)
 return cached

def script_native(run,template):
 """Client-sourced initialisation row for a scene object, or None.

 Only the two fields npc_initialization consumes are supplied: the record's
 script name (slot 2, the only slot the client catalogs populate for such
 objects) and no scripted max HP, matching the majority of catalog entries.
 """
 if type(template) is not int:return None
 signature=scene_signature(run)
 if signature is None:return None
 from els_server.game_data import client_data
 try:native=client_data().npc(template)
 except (ValueError,KeyError):return None
 script=native.get('script');enum=native.get('enum')
 if not isinstance(script,str) or not script.endswith('.lua') or not isinstance(enum,str):return None
 # The object must belong to this dungeon's own script family...
 if not script.upper().startswith(signature+'_'):return None
 # ...its enum must name the same object as its script...
 if enum.rsplit('.',1)[-1]!='NUI_'+script[:-4]:return None
 # ...only scene controllers qualify, because the combat class carries real
 # actors that must arrive through the pinned READY_NPC lists...
 if native.get('class_id')!=SCENE_CLASS:return None
 # ...a template the graph already declares is a static actor, and a second
 # dynamic copy would take a fresh key and break its death accounting...
 if template in declared_templates(run):return None
 # ...and the script must be one of the two proven dynamic shapes.
 if not PART_PANEL.match(script.upper()) and script not in run.catalog.manifest['source_sha256']:return None
 return dict(strings=['','',script,'','',''],script_max_hp=None,local_hp=None)

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x2ce or s.dungeon_run is None:return None
 run=s.dungeon_run
 if type(sequence) is not int or not 1<=sequence<2**32:return [summon_ack(-1)]
 digest=hashlib.sha256(event.payload).digest();old=run.dynamic_requests.get(sequence)
 if old is not None:return [summon_ack(0 if old==digest else -1)]
 if (s.phase!='dungeon_active' or not s.population_test or not s.dungeon_substage_synced or s.clear_notified
     or s.part_end_notified):return [summon_ack(-1)]
 allowed=set(run.graph['stages'][str(run.stage)]['allowed_summons'])
 owners={0,2**64-1,s.account.uid,*run.reserved_keys,*s.summon_keys}
 def validate(dto):
  key,template=struct.unpack_from('<ii',dto)
  if key!=-1:raise ValueError('NPC create key')
  if template not in allowed and script_native(run,template) is None:raise ValueError('NPC not declared by current encounter')
  if struct.unpack_from('<Q',dto,0x6d)[0] not in owners:raise ValueError('NPC creator outside current encounter')
  if dto[8] not in (0,1,2) or any(dto[o] not in (0,1) for o in (0x4e,0x54,0x61,0x65,0x66)):raise ValueError('NPC flag bound')
  if not all(math.isfinite(v) and abs(v)<=100000 for v in struct.unpack_from('<fff',dto,9)):raise ValueError('NPC spawn position bound')
 try:rows=decode(event.payload,validate)
 except ValueError:return None  # Preserve the existing player-sentry decoder.
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
  run.dynamic_requests[sequence]=digest
  return [summon_ack()]
 if any(struct.unpack_from('<i',r,4)[0]==384 and struct.unpack_from('<Q',r,0x6d)[0]==s.account.uid for r in rows):return None
 if len(run.dynamic_requests)>=4096:return [summon_ack(-1)]
 # The native scene has 80 concurrent slots, not 80 lifetime identities.
 # Retired records remain available for duplicate death acknowledgements.
 if occupied_slots(s)+len(rows)>80:return [summon_ack(-1)]
 try:free=run.new_npc_keys(len(rows),s.summon_keys)
 except ValueError:return [summon_ack(-1)]
 entries=[];wires=[];initial=[]
 for dto,key in zip(rows,free):
  template=struct.unpack_from('<i',dto,4)[0];boss=bool(dto[0x61])
  native=run.catalog._data['npcs'].get(str(template)) or script_native(run,template)
  if native is None:return [summon_ack(-1)]
  hp=native['script_max_hp'] or (5000 if boss else 500)
  struct.pack_into('<i',dto,0,key)
  init=npc_initialization(run.catalog,template,hp,native=native);wire=encode_npc(dto,0)
  entries.append(dict(key=key,template=template,key_code=struct.unpack_from('<i',dto,0x4f)[0],active=bool(dto[0x4e]),team=dto[8],ally=bool(dto[0x66]),no_drop=True,boss=boss,hp=hp,dynamic=True,wire=wire,init=init))
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
 run.current['npcs'].extend(entries);run.dynamic_requests[sequence]=digest
 return [summon_ack(),packet]
