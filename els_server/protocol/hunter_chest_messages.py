"""Reuse current2D0/AF profession map/CF/D0/D2/D3 and genuine4C4 only."""
import copy,struct
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain.dungeon_lifecycle import empty_reward_death_notice
from els_server.protocol.profession_messages import level_update

def spawn(run,source):
 from els_server.domain.dungeon_routes import npc_initialization
 from els_server.domain.dungeon_npcs import resource_dto,encode_npc
 from els_server.domain.hunter_chest_rules import NAMES
 from els_server.protocol.npc_uid_map import uid_translation_vector
 template,key=source['template'],source['npc_key']
 catalog=copy.copy(run.catalog);catalog._data=dict(run.catalog._data)
 catalog._data['npcs']={**catalog._data['npcs'],str(template):dict(strings=NAMES[template],script_max_hp=None,local_hp=500)}
 raw=bytearray.fromhex(catalog._data['spawn_seed']);struct.pack_into('<iii',raw,0,key,template,source['key_code'])
 struct.pack_into('<i',raw,0x28,source['start_point']);struct.pack_into('<3f',raw,0x30,*source['offset'])
 raw[0x2c]=1;raw[0x2d]=0;raw[0x3c]=0;raw[0x44]=0;raw[0x48]=1;raw[0x50]=0
 init=npc_initialization(catalog,template,500);wire=encode_npc(resource_dto(raw),0)
 actor=dict(key=key,template=template,key_code=source['key_code'],active=True,team=0,ally=False,no_drop=True,boss=False,hp=500,start_point=source['start_point'],offset=source['offset'],wire=wire,init=init,hunter_source=source)
 uid_map=uid_translation_vector(((key,template),))
 event=Event(0x201,kind=0x2d0,payload=struct.pack('>I',1)+wire+bytes(8)+uid_map+struct.pack('>Ii',1,key)+init+bytes(8))
 encode_event(event);return actor,event

def death(key,killer,gains):
 # 83E630's second map DAF020 is map<u64,i32>; native current-UID lookup
 # 1AB03E2 -> 2DF8F70 consumes it independently of character XP's first map.
 if len(gains)>4 or any(type(uid)is not int or not 1001<=uid<2**63 or type(xp)is not int or not 0<xp<2**31 for uid,xp in gains.items()):raise ValueError('Hunter AF profession map')
 base=empty_reward_death_notice(key,killer)
 return Event(0x201,kind=0xaf,payload=base.payload[:21]+struct.pack('>I',len(gains))+b''.join(struct.pack('>Qi',uid,xp)for uid,xp in sorted(gains.items()))+base.payload[25:])

def level(owner,before,after):
 return [Event(0x201,kind=0x4c4,payload=level_update(owner,after,{}))]if after.level>before.level else []
