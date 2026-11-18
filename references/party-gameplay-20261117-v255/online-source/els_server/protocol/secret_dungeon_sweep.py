"""Original 2FD41D0 request and 2F8B7A0 acknowledgement."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import empty_record,record


def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=12:
        raise ValueError('Secret sweep native request length')
    uid,stage=struct.unpack('>Qi',payload)
    if not 0<uid<2**63 or not 1<=stage<=6:
        raise ValueError('Secret sweep item/stage')
    return uid,stage


def acknowledgement(changes=(),ed=0,result=0):
    delta=struct.pack('>I',len(changes))+b''.join(
        empty_record(*position) if item is None else record(item) for position,item in changes)
    return Event(0x201,kind=0xc10,payload=struct.pack('>i',result)+delta+struct.pack('>Q',ed))
