"""Original4B9 code events and their per-group period records."""
from dataclasses import dataclass,replace
import struct
from els_server.protocol.protocol_codec import Event

@dataclass(frozen=True)
class CodeEntry:
    enabled: bool
    starts: int
    ends: int
    label: str = ''
    parameters: tuple = ()
    periods: tuple = ()

def _record(row):
    if not isinstance(row,CodeEntry)or type(row.enabled)is not bool or any(type(v)is not int or not -(2**63)<=v<2**63 for v in(row.starts,row.ends)):
        raise ValueError('Invalid code-event state')
    if type(row.label)is not str or type(row.parameters)is not tuple or len(row.parameters)>64:raise ValueError('Invalid code-event metadata')
    label=row.label.encode('utf-16le')
    if len(label)>512 or any(type(v)is not int or not -(2**31)<=v<2**31 for v in row.parameters):raise ValueError('Code-event metadata bound')
    return struct.pack('>BqqI',row.enabled,row.starts,row.ends,len(label))+label+struct.pack('>I',len(row.parameters))+b''.join(struct.pack('>i',v)for v in row.parameters)

def notice(rows):
    if type(rows)is not dict or len(rows)>256:raise ValueError('Explicit bounded code-event snapshot required')
    data=struct.pack('>I',len(rows));grouped=[]
    for code,row in sorted(rows.items()):
        if type(code)is not int or not 0<code<2**31:raise ValueError('Invalid code-event identity')
        data+=struct.pack('>i',code)+_record(row)
        if type(row.periods)is not tuple or len(row.periods)>64:raise ValueError('Code-event period records')
        if row.periods:grouped.append((code,row.periods))
    # The two unrelated sets stay empty. 2C221A0 -> 2C3FCA0 reads this last
    # map of packed record vectors, used by sale code529.
    data+=bytes(8)+struct.pack('>I',len(grouped))
    for code,periods in grouped:
        data+=struct.pack('>iI',code,len(periods))
        for row in periods:
            data+=_record(row)
            if row.periods:raise ValueError('Nested code-event periods')
    if len(data)>65536:raise ValueError('Code-event packet bound')
    return Event(0x201,kind=0x4b9,payload=data)

def _read_record(payload,offset):
    if offset+21>len(payload):raise ValueError('Truncated code-event record')
    enabled,starts,ends,size=struct.unpack_from('>BqqI',payload,offset);offset+=21
    if enabled not in(0,1)or size>512 or size%2 or offset+size+4>len(payload):raise ValueError('Invalid code-event record')
    label=payload[offset:offset+size].decode('utf-16le');offset+=size
    n,=struct.unpack_from('>I',payload,offset);offset+=4
    if n>64 or offset+n*4>len(payload):raise ValueError('Code-event parameter bound')
    parameters=struct.unpack_from('>'+'i'*n,payload,offset);offset+=n*4
    return CodeEntry(bool(enabled),starts,ends,label,parameters),offset

def read(payload):
    if type(payload)is not bytes or not 16<=len(payload)<=65536:raise ValueError('Code-event snapshot bound')
    count,=struct.unpack_from('>I',payload);offset=4;rows={}
    if count>256:raise ValueError('Code-event count bound')
    for _ in range(count):
        if offset+4>len(payload):raise ValueError('Truncated code-event identity')
        code,=struct.unpack_from('>i',payload,offset);offset+=4
        if not 0<code<2**31 or code in rows:raise ValueError('Invalid code-event identity')
        rows[code],offset=_read_record(payload,offset)
    if offset+12>len(payload)or payload[offset:offset+8]!=bytes(8):raise ValueError('Other code-event sets require an explicit merger')
    count,=struct.unpack_from('>I',payload,offset+8);offset+=12;seen=set()
    if count>256:raise ValueError('Code-event period groups')
    for _ in range(count):
        if offset+8>len(payload):raise ValueError('Truncated code-event period group')
        code,n=struct.unpack_from('>iI',payload,offset);offset+=8
        if code not in rows or code in seen or n>64:raise ValueError('Code-event period group identity')
        seen.add(code);periods=[]
        for _ in range(n):
            row,offset=_read_record(payload,offset);periods.append(row)
        rows[code]=replace(rows[code],periods=tuple(periods))
    if offset!=len(payload):raise ValueError('Trailing code-event data')
    return rows

def window_request(payload):
    if type(payload)is not bytes or payload:raise ValueError('OriginalD2A request is empty')

def window_reply():
    # Original1361630 ->13643B0 consumes onei32. Result is not a UI gate.
    return Event(0x201,kind=0xd2b,payload=bytes(4))
