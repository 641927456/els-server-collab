"""Original finite6E7 mode5/6 and6E8 full-record preview/confirm bodies."""
import struct
from els_server.protocol.protocol_codec import Event

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=38:raise ValueError('Engraving request length')
    uid,n,group,count,component,source,flag,mode,tail=struct.unpack('>QIiIiQBiB',payload)
    if (not 0<uid<2**63 or not 0<=source<2**63 or source==uid or (n,count,flag,tail)!=(1,1,0,0) or group not in (14,15,16) or not 0<=component<3 or mode not in (5,6) or (mode==5 and source==0)):raise ValueError('Engraving request fields/debug/free-ticket flags')
    return uid,group-14,component,source,mode

def body(uid,line,component,source,mode):
    value=struct.pack('>QIiIiQBiB',uid,1,14+line,1,component,source,0,mode,0);request(value);return value

def acknowledge(uid=0,ed=0,changes=(),*,mode=5,preview=0,result=0):
    from els_server.domain.fashion_state import record,empty_record
    if any(type(v) is not int or not 0<=v<2**63 for v in (uid,ed)) or type(mode) is not int or mode not in (5,6) or type(preview) is not int or not 0<=preview<=210 or (mode==6 and preview):raise ValueError('Engraving acknowledgement bounds')
    if type(result) is not int or not -2**31<=result<2**31:raise ValueError('Engraving result')
    rows=list(changes)
    if len(rows)>4 or len({tuple(p) for p,i in rows})!=len(rows):raise ValueError('Engraving changed positions')
    wire=struct.pack('>iQQI',result,uid,ed,len(rows))+b''.join(empty_record(*p) if i is None else record(i) for p,i in rows)+struct.pack('>iiiI',mode,preview,0,0)
    return Event(0x201,kind=0x6e8,payload=wire)
