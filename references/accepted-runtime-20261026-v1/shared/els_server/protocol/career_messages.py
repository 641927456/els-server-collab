"""Current-build 219/21A item use and 29F career notification."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import empty_record,record
from els_server.domain.skill_state import record as skill_record

def use_request(payload):
    # C595C0: item UID, optional target UID, two ints, wstring, bool.
    # Career consumables use no secondary item, string or extra parameters.
    if not isinstance(payload,bytes) or len(payload)!=29:raise ValueError('Career use request length')
    uid,target,a,b,n,flag=struct.unpack('>QQiiIB',payload)
    if not 0<uid<2**63 or target or a or b or n or flag:raise ValueError('Unsupported career item use parameters')
    return uid

def use_ack(changes=(),template=0,ed=0,result=0):
    # 234B140: result, inventory delta, three ints, ED and reserved uint64.
    delta=struct.pack('>I',len(changes))+b''.join(empty_record(*pos) if item is None else record(item) for pos,item in changes)
    return Event(0x201,kind=0x21a,payload=struct.pack('>i',result)+delta+struct.pack('>iiiQQ',template,0,0,ed,0))

def career_notice(character,location,slots,economy,items):
    from els_server.protocol.local_messages import character_unit
    from els_server.domain.skill_rules import learned_skills
    # B9C380 / kind29F: complete unit, learned skills (DAF5B0), int vector,
    # quest vector (DB60F0), quest-state vector (DD6E80). No GM acknowledgement.
    ranks=learned_skills(character)
    body=character_unit(location,True,slots,economy,items,character)
    body+=struct.pack('>I',len(ranks))+b''.join(skill_record(v,level) for v,level in ranks.items())+bytes(12)
    return Event(0x201,kind=0x29f,payload=body)

def stage_notice(character):
    from els_server.domain.character_rules import transcendental_stage
    return Event(0x201,kind=0x59f,payload=struct.pack('>ii',0,transcendental_stage(character)))
