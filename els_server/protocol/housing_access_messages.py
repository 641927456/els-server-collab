"""Current941 lifetime notification and exact30 DTO1DD cold projection."""
import struct
from els_server.protocol.protocol_codec import Event

def lifetime(value):
    if type(value)is not int or not 0<=value<2**63:raise ValueError('Housing native lifetime')
    return value

def notice(value):return Event(0x201,kind=0x941,payload=struct.pack('>iQ',0,lifetime(value)))

def patch_initialization(payload,value):
    lifetime(value)
    if type(payload)is not bytes or len(payload)!=216:raise ValueError('Housing30 unreviewed profile')
    probe=bytearray(payload);probe[131]=0;probe[181:193]=bytes(12)
    if any(probe)or payload[131]not in(0,1)or not 0<=struct.unpack_from('>i',payload,181)[0]<=3:
        raise ValueError('Housing30 nonempty unreviewed profile')
    return payload[:185]+struct.pack('>Q',value)+payload[193:]
