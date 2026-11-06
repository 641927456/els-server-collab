"""Native 1323CC0 / 234C870 circuit operation, mode16 only."""
import struct
from els_server.protocol.protocol_codec import Event


def request(payload):
    if not isinstance(payload,bytes) or not 26<=len(payload)<=218:
        raise ValueError('Circuit request size')
    uid,count,group,n=struct.unpack_from('>QIiI',payload)
    if not 0<uid<2**63 or count!=1 or group!=28 or not 1<=n<=16 or len(payload)!=26+12*n:
        raise ValueError('Circuit target/group/count')
    slots={};offset=20
    for _ in range(n):
        slot,material=struct.unpack_from('>iQ',payload,offset);offset+=12
        if not 0<=slot<16 or slot in slots or not 0<material<2**63:
            raise ValueError('Circuit slot/material identity')
        slots[slot]=material
    flag,mode,tail=struct.unpack_from('>BiB',payload,offset)
    if flag not in (0,1) or mode!=16 or tail:
        raise ValueError('Circuit mode/flags')
    return uid,slots,bool(flag)


def acknowledgement(uid=0,ed=0,changes=(),result=0):
    from els_server.domain.fashion_state import record,empty_record
    if any(type(v) is not int or not 0<=v<2**63 for v in (uid,ed)):
        raise ValueError('Circuit acknowledgement identity/balance')
    if type(result) is not int or not -2**31<=result<2**31:
        raise ValueError('Circuit acknowledgement result')
    rows=list(changes)
    if len(rows)>17 or len({tuple(pos) for pos,item in rows})!=len(rows):
        raise ValueError('Circuit update count/positions')
    # Native DTO+4 target UID; +C balance (22EEEC5 -> FEB6E0).
    wire=struct.pack('>iQQI',result,uid,ed,len(rows))
    wire+=b''.join(empty_record(*pos) if item is None else record(item) for pos,item in rows)
    # Circuit UI does not use the other modes' preview fields. Neutral native tails.
    wire+=struct.pack('>iiiI',16,0,0,0)
    return Event(0x201,kind=0x6e8,payload=wire)
