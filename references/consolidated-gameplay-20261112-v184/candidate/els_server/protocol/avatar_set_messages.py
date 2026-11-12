"""Native BFC/BFD and 788 selection restoration.

Saved selections retain their original canonical context zero. The preset
adapter exposes that existing equipment as native page 1 without rewriting
saved rows or granting additional equipment pages.
"""
import struct
from els_server.protocol.protocol_codec import Event

class ApplyShapeError(ValueError):
    def __init__(self, reason, rows):
        super().__init__(reason)
        self.shape = {
            'contexts': [context if 0 <= context <= 65535 else None for context, _, _, _ in rows],
            'sides': [side if 0 <= side <= 1 else None for _, side, _, _ in rows],
            'slots': [slot if -1 <= slot <= 10 else None for _, _, slot, _ in rows],
            'set_id_shapes': [min(set_id, 1) if set_id >= -1 else -2 for _, _, _, set_id in rows],
        }

def request(payload,*,context=0):
    if type(payload) is not bytes or len(payload)!=100 or struct.unpack_from('>I',payload)[0]!=6:
        raise ValueError('Avatar Apply requires exactly six records')
    rows=tuple(struct.unpack_from('>iiii',payload,4+16*i) for i in range(6))
    if any(r[0]!=context for r in rows):
        raise ApplyShapeError('Avatar Apply base context', rows)
    if any(r[1] not in (0,1) for r in rows):
        raise ApplyShapeError('Avatar Apply character side', rows)
    if {r[2] for r in rows}!=set(range(6)):
        raise ApplyShapeError('Avatar Apply slot indices', rows)
    if any(r[3]<0 for r in rows):
        raise ApplyShapeError('Avatar Apply negative set ID', rows)
    if len({r[1] for r in rows})!=1:raise ValueError('Mixed avatar sides')
    selected=[r[3] for r in rows if r[3]]
    if len(selected)!=len(set(selected)):raise ValueError('Repeated avatar set')
    return tuple(sorted(rows,key=lambda r:r[2]))

def acknowledgement(result=2960):
    return Event(0x201,kind=0xbfd,payload=struct.pack('>i',result))

def empty_restoration(*,page=0,total=0):
    return Event(0x201,kind=0x788,payload=struct.pack('>iBBII',0,page,total,0,0))

def restoration(rows,*,page=0,total=0):
    # 2BE03D0: result, current byte, secondary byte, vector of presets,
    # map<int,vector<four signed ints>>.23C75B0 flattens rows then sorts slots.
    rows=tuple(rows)
    if any(len(r)!=4 or any(type(v) is not int for v in r) or r[0]!=0 or r[1] not in (0,1) for r in rows):raise ValueError('Invalid saved avatar fields')
    rows=tuple(sorted(rows,key=lambda r:r[2]))
    for side in (0,1):
        subset=tuple(r for r in rows if r[1]==side)
        if subset:request(struct.pack('>I',len(subset))+b''.join(struct.pack('>iiii',*r) for r in subset))
    if len(rows) not in (6,12):raise ValueError('Incomplete saved avatar rows')
    body=struct.pack('>iBBIIiI',0,page,total,0,1,page,len(rows))
    return Event(0x201,kind=0x788,payload=body+b''.join(struct.pack('>iiii',page,*r[1:]) for r in rows))
