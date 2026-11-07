"""Native BFC/BFD and base-context 788 selection restoration.

This server has no equipment-preset switch/unlock route. Its native role
starts at context zero. Restoring selections preserves that zero/empty preset
state; it does not grant pages or synthesize opaque preset metadata.
"""
import struct
from els_server.protocol.protocol_codec import Event

def request(payload):
    if type(payload) is not bytes or len(payload)!=100 or struct.unpack_from('>I',payload)[0]!=6:
        raise ValueError('Avatar Apply requires exactly six records')
    rows=tuple(struct.unpack_from('>iiii',payload,4+16*i) for i in range(6))
    if {r[2] for r in rows}!=set(range(6)) or any(r[0]!=0 or r[1] not in (0,1) or r[3]<0 for r in rows):
        raise ValueError('Avatar base context/side/slots')
    if len({r[1] for r in rows})!=1:raise ValueError('Mixed avatar sides')
    selected=[r[3] for r in rows if r[3]]
    if len(selected)!=len(set(selected)):raise ValueError('Repeated avatar set')
    return tuple(sorted(rows,key=lambda r:r[2]))

def acknowledgement(result=-1):
    return Event(0x201,kind=0xbfd,payload=struct.pack('>i',result))

def restoration(rows):
    # 2BE03D0: result, current byte, secondary byte, vector of presets,
    # map<int,vector<four signed ints>>.23C75B0 flattens rows then sorts slots.
    rows=tuple(rows)
    if any(len(r)!=4 or any(type(v) is not int for v in r) or r[0]!=0 or r[1] not in (0,1) for r in rows):raise ValueError('Invalid saved avatar fields')
    rows=tuple(sorted(rows,key=lambda r:r[2]))
    for side in (0,1):
        subset=tuple(r for r in rows if r[1]==side)
        if subset:request(struct.pack('>I',len(subset))+b''.join(struct.pack('>iiii',*r) for r in subset))
    if len(rows) not in (6,12):raise ValueError('Incomplete saved avatar rows')
    body=struct.pack('>iBBIIiI',0,0,0,0,1,0,len(rows))
    return Event(0x201,kind=0x788,payload=body+b''.join(struct.pack('>iiii',*r) for r in rows))
