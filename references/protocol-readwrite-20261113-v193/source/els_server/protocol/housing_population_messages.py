"""Original328F640/328F7D0 room population, distinct from town227 readiness."""
import math,struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.protocol.social_messages import appearance_item
from els_server.protocol.character_custom_messages import actor_map


def request(payload):
    if type(payload)is not bytes or len(payload)!=15:
        raise ValueError('Housing92E original position')
    # 328F6FC ->31BF6D0 ->31C0D90 writes float3, byte, uint16.
    # The trailing native context has no position or admission authority.
    *xyz,_context,_auxiliary=struct.unpack('>fffBH',payload)
    xyz=tuple(xyz)
    if any(not math.isfinite(v)or abs(v)>1000000 for v in xyz):
        raise ValueError('Housing92E finite position')
    return xyz


def member(character,xyz,items):
    # DA4EB0 -> 13D DTO;2448BE0 requires the actual self UID at08 to
    # call the original21460E0 self-actor factory. An empty list cannot do so.
    # Unimplemented optional fields retain2C44880 constructor values.
    name=character['name'];uid=character['uid']
    raw=struct.pack('>QQ',0,uid)+wstring('')+b'\0'+wstring(name)
    raw+=struct.pack('>HfffQHi',0,*xyz,0,character['unit_class'],0)
    preference=0
    if character['unit_type']==10:
        from els_server.protocol.luciel_messages import active_preference
        preference=active_preference(character)
    raw+=struct.pack('>bbBii',preference,0,character['level'],character.get('title',0),0)
    # DA4EB0+78 ->8757A0 ->UserInfo+2690, matching the town guild-name field.
    guild=character.get('guild_membership')
    raw+=wstring(guild['name']if guild is not None else'')+struct.pack('>bBQi',0,0,0,0)
    from els_server.protocol.achievement_messages import status as achievement_status
    raw+=(achievement_status(**character['achievement_status'])if 'achievement_status'in character else bytes(4+4+1))
    raw+=struct.pack('>iiibiii',0,0,0,0,0,0,0)  #DB0D10, exact25-byte child.
    raw+=actor_map(character.get('character_custom',{}).get('selected',{}))
    worn=[item for item in items if item['group']==9]
    raw+=struct.pack('>I',len(worn))+b''.join(appearance_item(item,native_instance=True)for item in worn)
    raw+=bytes(4)+struct.pack('>iB',-1,0)+bytes(4)
    return raw


def ready(character,xyz,items,*,result=0):
    #2B4F560: result, vector<DA4EB0>, three optional native maps.
    rows=b''if character is None else member(character,xyz,items)
    raw=struct.pack('>iI',(2436) if result == -1 else result,int(character is not None))+rows+bytes(12)
    if len(raw)>65536:raise ValueError('Housing92F payload bound')
    return Event(0x201,kind=0x92f,payload=raw)
