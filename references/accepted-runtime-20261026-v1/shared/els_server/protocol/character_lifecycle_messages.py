"""Native CN DX11 48A/27 schedule, 598/599 restore, 59A/59B final delete."""
import struct
from datetime import datetime,timezone,timedelta
from els_server.protocol.local_messages import i32,u32,wstring
from els_server.protocol.protocol_codec import Event
def request(payload,allow_opaque=False):
    if len(payload)!=20:raise ValueError('Character lifecycle request length')
    uid,unused,server=struct.unpack('>QQi',payload)
    if not 1001<=uid<2**63 or (unused!=0 and not allow_opaque) or server!=1:raise ValueError('Character lifecycle request identity')
    return uid
def schedule_ack(uid=0,result=0,until=0,restore_at=0,error_until=0):
    # 138BED0: result,Q,u32,i32,string,u8,u16,Q,Q,Q,i32,string,string.
    body=i32(result)+struct.pack('>Q',uid)+bytes(8)+wstring('')+bytes(3)
    # 138BED0's 0x9B6 branch parses the final string as creation time using
    # 374470, then adds 72h. An empty string renders 1970-01-04 even when the
    # preceding numeric error deadline is correct. CN wall time is UTC+8.
    created=(datetime.fromtimestamp(error_until-3*86400,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
             if result==0x9b6 and error_until>=3*86400 else '')
    body+=struct.pack('>QQQ',error_until,until,restore_at)+i32(0)+wstring('')+wstring(created)
    return Event(0x201,kind=0x27,payload=body)
def restore_ack(uid=0,result=0,until=0):
    # 139A420: result, UID, earliest restore/delete timestamp.
    return Event(0x201,kind=0x599,payload=i32(result)+struct.pack('>QQ',uid,until))
def finalize_ack(uid=0,result=0,selection=None,until=0):
    # 1399040: result,Q,u32,i32,string,u8,u16,Q,Q,i32,i32,
    # vector<Q> (deployed), list<Q> (complete order).
    s=selection or dict(deployed=[],order=[])
    body=i32(result)+struct.pack('>Q',uid)+bytes(8)+wstring('')+bytes(3)
    body+=struct.pack('>QQ',until,0)+bytes(8)
    for key in ('deployed','order'):body+=u32(len(s[key]))+b''.join(struct.pack('>Q',v) for v in s[key])
    return Event(0x201,kind=0x59b,payload=body)
