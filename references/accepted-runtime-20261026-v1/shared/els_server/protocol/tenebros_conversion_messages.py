"""Native B0E writer / B0F full-item consumer; no random identification."""
import struct
from els_server.domain.fashion_state import record,empty_record
from els_server.protocol.protocol_codec import Event


def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=24:
        raise ValueError('Tenebros select request size')
    target,slot,option,ticket=struct.unpack('>QiiQ',payload)
    if (not 0<target<2**63 or not 0<ticket<2**63 or target==ticket
        or slot not in (0,1,2) or not 0<option<2**31):
        raise ValueError('Tenebros select request identity')
    return target,slot,option,ticket


def acknowledgement(changes=(),*,result=0):
    # 2C51D60 parses i32,Q,DD46E0 records. The parsed Q has no subsequent use
    # in this complete consumer; its economic meaning is unproved. Zero is
    # deliberately an unused scalar, never an invented ED/option balance.
    payload=struct.pack('>iQI',result,0,len(changes))+b''.join(
        empty_record(*point) if item is None else record(item)
        for point,item in changes)
    return Event(0x201,kind=0xb0f,payload=payload)
