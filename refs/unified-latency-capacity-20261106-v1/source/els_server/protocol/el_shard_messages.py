"""Current native2359DF0/227F840 El Shard extraction DTOs."""
import struct
from els_server.domain.fashion_state import record, empty_record

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=12:
        raise ValueError('El Shard extraction request size')
    uid,quantity=struct.unpack('>Qi',payload)
    if not 0<uid<2**63 or not 0<quantity<2**31:
        raise ValueError('El Shard extraction request fields')
    return uid,quantity

def acknowledgement(changes=(),rewards=None,*,result=0):
    rewards=rewards or {}
    return (struct.pack('>iI',result,len(changes))+
            b''.join(record(item) if item else empty_record(*position) for position,item in changes)+
            struct.pack('>I',len(rewards))+
            b''.join(struct.pack('>ii',template,quantity) for template,quantity in sorted(rewards.items())))
