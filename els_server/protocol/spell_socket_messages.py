"""Exact native 1323CC0 writer / 234C870 reader for paid preview and apply."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.fashion_state import record,empty_record

def request(payload):
    if not isinstance(payload,bytes)or len(payload)not in(18,38):raise ValueError('Mystic request width')
    uid,count=struct.unpack_from('>QI',payload)
    if not 0<uid<2**63:raise ValueError('Mystic target UID')
    flag,mode,reserved=struct.unpack_from('>BiB',payload,len(payload)-6)
    if flag!=0 or reserved!=0:raise ValueError('Mystic debug/free producer refused')
    if len(payload)==18 and count==0 and mode==4:return uid,None,None,None,mode
    if len(payload)!=38 or count!=1 or mode!=2:raise ValueError('Mystic original single-slot producer')
    group,n,slot,source=struct.unpack_from('>iIiQ',payload,12)
    if group not in(9,10,11,12)or n!=1 or not 0<=slot<(3 if group==12 else 9)or not 0<source<2**63 or source==uid:
        raise ValueError('Mystic source/color/slot')
    return uid,group,slot,source,mode

def acknowledgement(uid=0,ed=0,changes=(),*,mode,option=0,result=0):
    rows=list(changes)
    # Native order is result, ED, target UID. The generic artifact helper has
    # a different contract and is intentionally unchanged.
    body=struct.pack('>iQQI',result,ed,uid,len(rows))
    body+=b''.join(empty_record(*p)if item is None else record(item)for p,item in rows)
    body+=struct.pack('>iiiI',mode,option,0,0)
    return Event(0x201,kind=0x6e8,payload=body)
