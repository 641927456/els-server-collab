"""Current dual-UID971 request and972 complete inventory vector."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import record,empty_record

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=24:raise ValueError('Mystic exchange request width')
    left,right,group,index=struct.unpack('>QQii',payload)
    if not 0<left<2**63 or not 0<right<2**63 or left==right:raise ValueError('Two distinct signed63 instance UIDs required')
    # Native 322FC70 converts the UI step to zero-based before 326DE20 writes it.
    if (group not in (9,10,11,12) or
            (group==12 and not 0<=index<3) or (group!=12 and index!=-1)):
        raise ValueError('Invalid mystic exchange color/slot')
    return left,right,group,index

def acknowledgement(changes=(),result=0):
    return Event(0x201,kind=0x972,payload=struct.pack('>iI',(2856) if result in (-1, 2005) else result,len(changes))+
        b''.join(record(item) if item is not None else empty_record(*pos) for pos,item in changes))
