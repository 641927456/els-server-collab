"""8D1/8D2 operation16, distinct from 6E7 circuit installation mode16."""
import struct
from els_server.protocol.protocol_codec import Event

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=14:raise ValueError('Color request length')
    uid,mode,color=struct.unpack('>QiH',payload)
    if not 0<uid<2**63 or mode!=16 or color not in (1,2,3):raise ValueError('Color request identity/mode')
    return uid,color

def acknowledgement(uid=0,changes=(),result=0):
    from els_server.domain.fashion_state import record,empty_record
    if type(uid) is not int or not 0<=uid<2**63 or type(result) is not int or not -2**31<=result<2**31:raise ValueError('Color response identity/result')
    rows=list(changes)
    if len(rows)>16 or len({tuple(pos) for pos,item in rows})!=len(rows):raise ValueError('Color response positions')
    # Original 2282700 applies the full-record vector; map and ancillary vectors
    # have no color-branch consumers. DTO+4 is target UID, not a money balance.
    payload=struct.pack('>iQIIII',result,uid,0,0,0,len(rows))
    payload+=b''.join(empty_record(*pos) if item is None else record(item) for pos,item in rows)
    return Event(0x201,kind=0x8d2,payload=payload+struct.pack('>i',16))
