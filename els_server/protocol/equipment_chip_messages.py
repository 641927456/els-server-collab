"""Native mode15 installation and dedicated BB8/BB9 tuning bodies."""
import struct
from els_server.protocol.protocol_codec import Event

def installation(payload):
    if not isinstance(payload,bytes) or len(payload)!=38:raise ValueError('Chip installation body')
    uid,count,group,n,slot,source,flag,mode,tail=struct.unpack('>QIiIiQBiB',payload)
    if not 0<uid<2**63 or not 0<source<2**63 or uid==source or (count,group,n,slot,flag,mode,tail)!=(1,27,1,0,0,15,0):raise ValueError('Chip installation fields')
    return uid,source

def tuning(payload):
    if not isinstance(payload,bytes) or len(payload)!=12:raise ValueError('Chip tuning body')
    uid,cheat=struct.unpack('>Qi',payload)
    if not 0<uid<2**63 or cheat:raise ValueError('Chip tuning UID or unsupported cheat probability')
    return uid

def changes_wire(changes):
    from els_server.domain.fashion_state import record,empty_record
    rows=list(changes)
    if len(rows)>4 or len({tuple(pos) for pos,item in rows})!=len(rows):raise ValueError('Chip changed positions')
    return struct.pack('>I',len(rows))+b''.join(empty_record(*pos) if item is None else record(item) for pos,item in rows)

def bounds(uid,ed,result):
    if any(type(v) is not int or not 0<=v<2**63 for v in (uid,ed)) or type(result) is not int or not -2**31<=result<2**31:raise ValueError('Chip acknowledgement fields')

def install_ack(uid=0,ed=0,changes=(),result=0):
    bounds(uid,ed,result)
    return Event(0x201,kind=0x6e8,payload=struct.pack('>iQQ',result,uid,ed)+changes_wire(changes)+struct.pack('>iiiI',15,0,0,0))

def tuning_ack(uid=0,ed=0,changes=(),result=0,success=False):
    bounds(uid,ed,result)
    if type(success) is not bool:raise ValueError('Chip tuning success flag')
    return Event(0x201,kind=0xbb9,payload=struct.pack('>iBQ',result,int(success),ed)+changes_wire(changes))
