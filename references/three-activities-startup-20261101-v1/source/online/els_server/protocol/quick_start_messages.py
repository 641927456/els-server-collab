"""Pinned C55 user state and C56/C57 career choice; C58/C59 finish guide."""
import struct
from els_server.protocol.protocol_codec import Event

def user_state(uid=0,finished=False):
    # B7C170 caseC55 -> virtual508 -> BF1680 /13AD1A0:
    # Q, i32, three bools. UID and the second bool update native user data.
    return Event(0x201,kind=0xc55,payload=struct.pack('>QiBBB',uid,1,0,int(finished),0))

def career_request(payload):
    # Native2FD4550 writes exactly one i32 class identity.
    if type(payload)is not bytes or len(payload)!=4:raise ValueError('Quick Start career payload')
    return struct.unpack('>i',payload)[0]

def career_ack(quests=(),result=0):
    # Native2F92320: result and vector<i32> quests retired by the transition.
    return Event(0x201,kind=0xc57,payload=struct.pack('>iI',result,len(quests))+b''.join(struct.pack('>i',q)for q in quests))

def finish_ack(uid,result=0,finished=False):
    return Event(0x201,kind=0xc59,payload=struct.pack('>iQiBBB',result,uid,1,0,int(finished),0))
