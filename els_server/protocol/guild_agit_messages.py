"""Current C5CD81/B950A0, C4DB10 and DA42B0/30DE140 native layouts."""
import math,struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.social_messages import wstring,appearance_item

def entry_request(payload):
 if len(payload)!=20:raise ValueError('GuildAgit original4FB size')
 selector,x,y,z,destination=struct.unpack('>IfffI',payload)
 if selector!=0 or destination!=25000 or any(not math.isfinite(v)or abs(v)>1000000 for v in(x,y,z)):raise ValueError('GuildAgit own guild4FB')
 return x,y,z

def entered(position,*,result=0):
 # Opaque fields remain original constructed defaults. No guessed ownership
 # or economic semantics are assigned to fields ignored by B950A0.
 return Event(0x201,kind=0x4fc,payload=struct.pack('>iQ',result,0)+wstring('')+bytes(2)+wstring('')+bytes(4)+wstring('')+struct.pack('>fffi',*position,25000))

def loaded(*,result=0):return Event(0x201,kind=0x226,payload=struct.pack('>iiiii',result,25000,0,0,0))

def member(character,location,items=()):
 # Complete DA42B0, 0x22F DTO, empty optional native components. Offsets
 # are independently observed wire offsets with all variable fields empty.
 # 87FDC0 binds +08 UID, +10 name, +52 class, +54 stage, +5A level;
 # 20798E0 consumes +E9 xyz. Public worn items use original D9A9D0.
 raw=bytearray(247)
 struct.pack_into('>Q',raw,8,character['uid'])
 struct.pack_into('>H',raw,26,character['unit_class'])
 from els_server.domain.character_rules import transcendental_stage
 struct.pack_into('>i',raw,28,transcendental_stage(character))
 raw[34]=character['level']
 if character.get('unit_type')==10:
  from els_server.protocol.luciel_messages import active_preference
  raw[32]=active_preference(character)
 struct.pack_into('>i',raw,52,character.get('title',0))
 struct.pack_into('>fff',raw,97,*location['xyz'])
 struct.pack_into('>i',raw,173,-1) # original ctor +185 default
 worn=[i for i in items if i['group']==9]
 equipment=struct.pack('>I',len(worn))+b''.join(appearance_item(i,native_instance=True)for i in worn)
 return bytes(raw[:16])+wstring(character['name'])+bytes(raw[20:44])+equipment+bytes(raw[48:])

def ready(rows=(),*,result=0):return Event(0x201,kind=0x505,payload=struct.pack('>iI',result,len(rows))+b''.join(member(*r)for r in rows))
def added(row):return Event(0x201,kind=0x4fd,payload=member(*row))
def removed(uid):return Event(0x201,kind=0x500,payload=struct.pack('>Qi',uid,0))
