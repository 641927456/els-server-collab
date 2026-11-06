"""Original BBC two-UID request and BBD inventory-vector reply only.

Policy/eligibility are server transaction concerns; this remains the original codec.
"""
import struct
from els_server.protocol.protocol_codec import Event

def reset_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=16:raise ValueError('Chip reset request body')
    ticket,chip=struct.unpack('>QQ',payload)
    if not 0<ticket<2**63 or not 0<chip<2**63 or ticket==chip:raise ValueError('Chip reset owned UID bounds')
    return ticket,chip

def reset_ack(changes=(),result=0):
    from els_server.domain.fashion_state import record,empty_record
    if type(result) is not int or not -2**31<=result<2**31:raise ValueError('Chip reset result')
    rows=list(changes)
    if len(rows)>4 or len({tuple(pos) for pos,item in rows})!=len(rows):raise ValueError('Chip reset affected positions')
    wire=[]
    for pos,item in rows:
        if not isinstance(pos,(tuple,list)) or len(pos)!=2 or any(type(x) is not int for x in pos) or pos[0] not in (1,4) or not 0<=pos[1]<392:raise ValueError('Chip reset bag position')
        if item is not None and (item['group'],item['slot'])!=tuple(pos):raise ValueError('Chip reset position mismatch')
        wire.append(empty_record(*pos) if item is None else record(item))
    return Event(0x201,kind=0xbbd,payload=struct.pack('>iI',result,len(rows))+b''.join(wire))
