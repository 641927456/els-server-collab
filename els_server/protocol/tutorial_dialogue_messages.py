"""Pinned FD NPC interaction and complete FE detail response (21BA150/21B6CD0)."""
import struct
from els_server.protocol.protocol_codec import Event

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=4:raise ValueError('NPC interaction size')
    return struct.unpack('>i',payload)[0]

def acknowledgement(quest=0,*,result=0):
    if type(quest) is not int or type(result) is not int:raise ValueError('Tutorial dialogue reply')
    if quest not in (0,13,25600,28030,28120,28130,28210,28300,28310,28360,28430,28440,28530,28620,28630,28640,28650,28660,28670,28680,28690):
        from els_server.domain.town_dialogue import catalog
        if str(quest) not in catalog()['quests']:raise ValueError('Unsupported town dialogue reply')
    # result, detail quest, uint64, six empty delta containers, bool,
    # uint32-length empty wstring, native mode2, int32, two int64, bool.
    # These are empty deltas, never an inventory replacement or a reward.
    body=struct.pack('>iiQ',result,quest,0)+bytes(29)+b'\2'+bytes(21)
    return Event(0x201,kind=0xfe,payload=body)
