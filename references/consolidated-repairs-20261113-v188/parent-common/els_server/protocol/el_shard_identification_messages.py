"""Original206 UID+count and207 result/map/full-vector/absolute-ED."""
import struct
from els_server.domain.fashion_state import record,empty_record
def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=12:raise ValueError('Shard identification request size')
    uid,quantity=struct.unpack('>Qi',payload)
    if not 0<uid<2**63 or not 0<quantity<2**31:raise ValueError('Shard identification request fields')
    return uid,quantity
def acknowledgement(ed,changes=(),rewards=None,*,result=0):
    rewards=rewards or {}
    return(struct.pack('>iI',result,len(rewards))+
        b''.join(struct.pack('>ii',template,count)for template,count in sorted(rewards.items()))+
        struct.pack('>I',len(changes))+
        b''.join(record(item)if item else empty_record(*position)for position,item in changes)+struct.pack('>Q',ed))
