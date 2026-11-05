"""Original generic activity-list codec, isolated and inactive.

B7C170 kind2AF -> state vslot370/B90FA0 -> C4DA60 -> DA2C40.
Unknown fields retain DTO-offset names. No selected2026 campaign definition,
reward ID, eligibility, delivery policy or activation is supplied here.
"""
from dataclasses import dataclass
import math
import struct
from els_server.protocol.protocol_codec import Event

def integer(value,bits,signed=True):
    low=-(1<<(bits-1)) if signed else 0
    high=(1<<(bits-1))-1 if signed else (1<<bits)-1
    if type(value) is not int or not low<=value<=high:raise ValueError('Integer field out of range')
    return value

def text(value):
    if type(value) is not str:raise ValueError('Text field required')
    raw=value.encode('utf-16le')
    if len(raw)>1048576:raise ValueError('Local packet budget exceeded')
    return struct.pack('>I',len(raw))+raw

def float32(value):
    if type(value) not in (float,int) or not math.isfinite(value):raise ValueError('Finite float required')
    try:return struct.pack('>f',value)
    except (OverflowError,struct.error) as exc:raise ValueError('Float32 out of range') from exc

@dataclass(frozen=True)
class ActivityRecord:
    key: int
    code: int
    text_08: str
    float_28: float
    text_2c: str
    text_4c: str
    int_6c: int
    map_70: tuple[tuple[int,int,int], ...]
    category_80: int
    float_84: float
    float_88: float
    bits_8c: int
    bits_94: int
    int_9c: int
    bool_a0: bool
    pair_a1: tuple[int,int]

    def encode(self):
        i=lambda n:struct.pack('>i',integer(n,32))
        if type(self.map_70) is not tuple or any(type(x) is not tuple or len(x)!=3 for x in self.map_70):raise ValueError('Explicit immutable map triples required')
        keys=[integer(x[0],32) for x in self.map_70]
        if len(set(keys))!=len(keys):raise ValueError('Duplicate map keys')
        if type(self.bool_a0) is not bool:raise ValueError('Boolean field required')
        if type(self.pair_a1) is not tuple or len(self.pair_a1)!=2:raise ValueError('Explicit pair required')
        body=i(self.key)+i(self.code)+text(self.text_08)+float32(self.float_28)+text(self.text_2c)+text(self.text_4c)+i(self.int_6c)
        body+=struct.pack('>I',len(self.map_70))+b''.join(i(k)+i(v)+struct.pack('>h',integer(s,16)) for k,v,s in sorted(self.map_70))
        body+=i(self.category_80)+float32(self.float_84)+float32(self.float_88)
        body+=struct.pack('>QQ',integer(self.bits_8c,64,False),integer(self.bits_94,64,False))+i(self.int_9c)
        body+=bytes([self.bool_a0])+i(self.pair_a1[0])+i(self.pair_a1[1])
        if len(body)>1048576:raise ValueError('Local packet budget exceeded')
        return body

def activity_list_update(*,action,records):
    """0 selective replacement; 1 upsert; 2 remove in the primary tree.

    3 upserts and4 removes from the second tree. Caller owns policy.

    Removal still carries full original records. Category2/3/6/46 are
    preserved by action0's deletion pass, so this is not a universal clear.
    """
    if type(action) is not int or action not in (0,1,2,3,4):raise ValueError('Unknown update action')
    if type(records) is not tuple or any(type(x) is not ActivityRecord for x in records):raise ValueError('Explicit immutable records required')
    if len({r.key for r in records})!=len(records):raise ValueError('Duplicate activity keys')
    body=bytes([action])+struct.pack('>I',len(records))+b''.join(r.encode() for r in records)
    if len(body)>1048000:raise ValueError('Local packet budget exceeded')
    return Event(0x201,kind=0x2af,payload=body)
