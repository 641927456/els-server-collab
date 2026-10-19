"""Opt-in original population. Stats/intro remain an explicit local experiment."""
from els_server.paths import PROJECT_ROOT
import functools,hashlib,json,struct
from pathlib import Path
from els_server.domain.dungeon_npcs import resource_dto,encode_npc
from els_server.protocol.protocol_codec import Event
from els_server.game_data import client_data
ROOT=PROJECT_ROOT/'analysis/client-6c6b5180'
SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
def population(stage):
 if type(stage) is not int or stage not in range(3):raise ValueError('Unsupported population stage')
 # Definitions belong to the pinned client build, like ClientData's catalogs.
 # Cache only verified serialized data; callers still receive fresh nested
 # objects, so Boss-gauge overrides or diagnostics cannot alter later spawns.
 return json.loads(_verified_population(stage))

@functools.lru_cache(maxsize=3)
def _verified_population(stage):
 data=json.loads((ROOT/'population-test-fixture.json').read_text(encoding='utf8'))
 if data['client_sha256']!=SHA or data['map']!=30000 or not data['original_population'] or data['retail_stats'] or data['boss_flags_restored']:raise ValueError('Unsupported population profile')
 for name,digest in data['source_sha256'].items():
  if hashlib.sha256((ROOT/'resource-scripts'/name).read_bytes()).hexdigest()!=digest:raise ValueError('Population source changed')
 part=data['stages'][stage]
 if part['index']!=stage or part['part']!=0 or len(part['npcs'])!=(8,11,2)[stage]:raise ValueError('Population stage mismatch')
 for key,npc in enumerate(part['npcs']):
  definition=client_data().npc(npc['template'])
  if definition['enum']!=npc['source_group']['NPC_ID']['global']:raise ValueError('Population NPC definition mismatch')
  raw=bytes.fromhex(npc['resource_hex']);init=bytes.fromhex(npc['init_hex'])
  if (npc['key']!=key or struct.unpack_from('<ii',raw)!=(key,npc['template']) or
      encode_npc(resource_dto(raw),0).hex()!=npc['wire_hex'] or struct.unpack_from('>i',init)[0]!=npc['template']):raise ValueError('Population identity/wire mismatch')
 return json.dumps(part)
def substage(stage,boss_gauge=False):
 part=population(stage);npcs=part['npcs']
 if boss_gauge and stage==2:
  boss=npcs[0];source=boss['source_group']
  if boss['template']!=5 or source.get('HAVE_BOSS_GAGE')!={'global':'TRUE'} or source.get('BOSS_GAUGE_HP_LINES')!=1:raise ValueError('Unverified Boss gauge source')
  raw=bytearray.fromhex(boss['resource_hex'])
  # 107F480 resource44 -> actor1ABEB; resource58(u16) -> actor1ABEE.
  # 1693620 gates HP interpolation on the former and divides maximum HP
  # by the latter. Other intro/grade fields remain separately unverified.
  raw[0x44]=1;struct.pack_into('<H',raw,0x58,source['BOSS_GAUGE_HP_LINES'])
  npcs=[{**boss,'resource_hex':raw.hex(),'wire_hex':encode_npc(resource_dto(raw),0).hex()},*npcs[1:]]
 spawns=struct.pack('>IiII',1,0,0,len(npcs))+b''.join(bytes.fromhex(n['wire_hex']) for n in npcs)
 initialization=struct.pack('>I',len(npcs))+b''.join(struct.pack('>i',n['key'])+bytes.fromhex(n['init_hex']) for n in npcs)
 payload=struct.pack('>ii',stage,0)+spawns+bytes(9)+bytes(12)+bytes(8)+initialization+bytes(8)
 return Event(0x201,kind=0xb2,payload=payload)
