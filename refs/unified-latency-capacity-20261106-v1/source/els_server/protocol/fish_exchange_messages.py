"""Current House40256 manual223/224, one native recipe and explicit quantity."""
import struct
from els_server.protocol.purifier_exchange_messages import ExchangeRequest
from els_server.domain.fashion_state import record,empty_record

def request(payload):
    if not isinstance(payload,bytes)or len(payload)!=37:raise ValueError('Fish exchange request length')
    r=ExchangeRequest(*struct.unpack('>iQiiiiiBi',payload))
    if (r.house!=40256 or r.source_uid!=0 or r.source not in range(135933,135938)
        or r.exchange_type not in (1,2,3)or r.native_flag!=1 or r.native_index!=0
        or not 1<=r.quantity<=117600):raise ValueError('Fish exchange original manual mode')
    return r

def acknowledgement(ed,changes=(),rewards=(),*,result=0,exchange_type=3):
    if type(ed)is not int or not 0<=ed<2**63 or exchange_type not in (1,2,3):raise ValueError('Fish exchange ED/type')
    if result not in (0,-1)or len(changes)>1176 or len(rewards)>15:raise ValueError('Fish exchange response bounds')
    rows=b''.join(empty_record(*p)if item is None else record(item)for p,item in changes)
    if any(type(t)is not int or type(n)is not int or not 0<t<2**31 or not 0<n<2**31 for t,n in rewards):raise ValueError('Fish exchange output count')
    return (struct.pack('>iI',result,len(changes))+rows+struct.pack('>I',len(rewards))
        +b''.join(struct.pack('>ii',t,n)for t,n in rewards)+struct.pack('>BBQQ',1,exchange_type,0,ed))
