"""Original inventory + button: 47B/47C quote, 479/47A purchase."""
import struct
from els_server.domain.bag_capacity import PRODUCT_GROUPS
from els_server.protocol.protocol_codec import Event


def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=4:
        raise ValueError('Bag expansion request size')
    group,=struct.unpack('>i',payload)
    if group not in PRODUCT_GROUPS.values():
        raise ValueError('Unsupported expandable bag')
    return group


def quote_ack(cost=0,result=0):
    # 2276850 reads result:i32, cost:u64, reserved:i32 before AddPage_Show.
    return Event(0x201,kind=0x47c,payload=struct.pack('>iQi',result,cost,0))


def expansion_ack(group=0,ed=0,delta=0,result=0):
    # 234B840 -> 2276B20: result, absolute ED, map<int,int> DELTAS, i32.
    values=struct.pack('>Iii',1,group,delta) if delta else bytes(4)
    return Event(0x201,kind=0x47a,payload=struct.pack('>iQ',result,ed)+values+bytes(4))
