"""Original empty B71 request and B72 enhancement configuration reply.

BED440 sends the request and registers a B72 wait. BED520 reads i32 result,
map<i32,i32>, set<i32>, map<i32,set<i32>>, map<i32,i32>, set<i32>, in that order.
The native handler applies them to item-manager +370, +380, +390, +3A0, +3B0.
"""
import struct
from els_server.domain.enhancement_progress import LIMITS
from els_server.protocol.protocol_codec import Event


def acknowledgement(result=0):
    if type(result) is not int or result not in (0,-1):
        raise ValueError('Invalid enhancement configuration result')
    # Only the ordinary enhancement profile is implemented. No event-specific
    # override or exception entries are invented for the three auxiliary tables.
    gauge=LIMITS if result==0 else {}
    points={11:20} if result==0 else {}
    def mapping(rows):
        return struct.pack('>I',len(rows))+b''.join(struct.pack('>ii',k,v) for k,v in sorted(rows.items()))
    payload=(struct.pack('>i',result)+mapping(gauge)+struct.pack('>II',0,0)+
             mapping(points)+struct.pack('>I',0))
    return Event(0x201,kind=0xb72,payload=payload)
