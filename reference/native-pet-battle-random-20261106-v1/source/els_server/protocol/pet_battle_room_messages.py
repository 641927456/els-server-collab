"""Native34B pet room metadata; actor/transport admission belongs to the flow.

2D68DB0 selects CX2PetFightRoom for D9BCC0+95==13 and state30.
2B1C650 consumes show-world+A1; current PetFightGameData defines world1048.
Unconsumed category fields retain constructor zeros, not official-PvP rules.
"""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32,u32,wstring


WORLD=1048


def room_info(identity,bootstrap_port):
    if type(identity)is not int or not 1<=identity<2**63:
        raise ValueError('Pet battle room identity')
    if type(bootstrap_port)is not int or not 1<=bootstrap_port<=65535:
        raise ValueError('Pet battle relay bootstrap port')
    data=b'\0'+struct.pack('>Q',identity)+u32(0)+wstring('PetFight')
    data+=b'\4\1\0'+wstring('')+b'\2\2'
    data+=wstring('127.0.0.1')+struct.pack('>H',bootstrap_port)+wstring('')
    # D9BCC0 reads bool94, mode95, byte96 in that exact wire order.
    data+=b'\0\x0d\0'+i32(0)+b'\0\0'+struct.pack('>fhh',0,WORLD,WORLD)
    data+=bytes(8)+i32(0)+b'\0'+i32(0)+bytes(2)
    data+=bytes(8)*2+i32(0)+b'\0'
    data+=u32(0)+bytes(2)+i32(0)+bytes(2)+bytes(8)+u32(0)
    data+=b'\0'+i32(0)+bytes(8)*2
    return data


def admission(full_users,identity,bootstrap_port):
    """Two already-authorized (actor UID, FullUser bytes) in red/blue order."""
    if len(full_users)!=2:raise ValueError('Pet battle two native members')
    slots=[]
    for index,(owner,body)in enumerate(full_users):
        slots.append(bytes((index,4,int(index==0),1,0,0))+i32(index)+u32(1)
            +body+u32(0)+bytes(4))
    payload=room_info(identity,bootstrap_port)+u32(2)+b''.join(slots)+bytes(12)
    return Event(0x201,kind=0x34b,payload=payload)
