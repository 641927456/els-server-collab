"""Ordinary selected-reward essence: original 460/461 material messages.

This is the material operation, not a replacement combat/MP/cooldown engine.
Concentrated essence and effect31's additional material remain unsupported.
"""
import math,struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import empty_record,record

ORDINARY=(130208,723609,723610,723611)

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=22:raise ValueError('Essence request size')
    concentrated,mode,extra,skill,x,y,z=struct.unpack('>BBii3f',payload)
    if concentrated!=0 or mode!=0 or extra!=0:raise ValueError('Unsupported essence mode or extra-effect material')
    if skill<=0 or not all(math.isfinite(v) for v in (x,y,z)):raise ValueError('Essence skill or coordinate')
    return skill

def acknowledgement(changes=(),*,result=0,replayed=False):
    # Original 1AAE720: result,DD46E0 absolute inventory vector,bool,bool.
    # First bool selects actor+1A38 (concentrated branch), kept false here.
    # Second bool exits before inventory/actor mutation; used on local retries.
    return Event(0x201,kind=0x461,payload=struct.pack('>iI',result,len(changes))+b''.join(empty_record(*p) if i is None else record(i) for p,i in changes)+bytes((0,int(replayed))))
