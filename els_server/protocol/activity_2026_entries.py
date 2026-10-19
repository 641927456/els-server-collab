"""Original4B9 snapshots for the two selected code-event entries.

The final three containers remain explicitly empty in this provider. A caller
with another producer must merge its rows before emitting the replacement.
Unknown nonempty suffixes are rejected instead of silently discarded.
"""
from dataclasses import dataclass
import struct
from els_server.protocol.protocol_codec import Event


@dataclass(frozen=True)
class CodeEntry:
    enabled: bool
    starts: int
    ends: int
    label: str = ''
    parameters: tuple = ()


def notice(rows):
    if type(rows) is not dict or len(rows)>256:
        raise ValueError('Explicit bounded code-event snapshot required')
    data=struct.pack('>I',len(rows))
    for code,row in sorted(rows.items()):
        if type(code) is not int or not 0<code<2**31 or not isinstance(row,CodeEntry):
            raise ValueError('Invalid code-event row')
        if type(row.enabled) is not bool or any(type(v) is not int or not -(2**63)<=v<2**63 for v in (row.starts,row.ends)):
            raise ValueError('Invalid code-event state')
        if type(row.label) is not str or type(row.parameters) is not tuple or len(row.parameters)>64:
            raise ValueError('Invalid code-event metadata')
        label=row.label.encode('utf-16le');size=len(label)
        if size>512 or any(type(v) is not int or not -(2**31)<=v<2**31 for v in row.parameters):
            raise ValueError('Code-event metadata bound')
        data+=struct.pack('>iBqqI',code,row.enabled,row.starts,row.ends,size)+label+struct.pack('>I',len(row.parameters))
        data+=b''.join(struct.pack('>i',v) for v in row.parameters)
    data+=bytes(12)
    if len(data)>65536:raise ValueError('Code-event packet bound')
    return Event(0x201,kind=0x4b9,payload=data)


def read(payload):
    if type(payload) is not bytes or not 16<=len(payload)<=65536:raise ValueError('Code-event snapshot bound')
    count,=struct.unpack_from('>I',payload);offset=4;rows={}
    if count>256:raise ValueError('Code-event count bound')
    for _ in range(count):
        if offset+25>len(payload):raise ValueError('Truncated code-event row')
        code,enabled,starts,ends,size=struct.unpack_from('>iBqqI',payload,offset);offset+=25
        if not 0<code<2**31 or code in rows or enabled not in (0,1) or size>512 or size%2 or offset+size+4>len(payload):
            raise ValueError('Invalid code-event row')
        label=payload[offset:offset+size].decode('utf-16le');offset+=size
        n,=struct.unpack_from('>I',payload,offset);offset+=4
        if n>64 or offset+n*4>len(payload):raise ValueError('Code-event parameter bound')
        parameters=struct.unpack_from('>'+'i'*n,payload,offset);offset+=n*4
        rows[code]=CodeEntry(bool(enabled),starts,ends,label,parameters)
    if payload[offset:]!=bytes(12):raise ValueError('Other code-event containers require an explicit merger')
    return rows


def window_request(payload):
    if type(payload) is not bytes or payload:raise ValueError('OriginalD2A request is empty')


def window_reply():
    # Original1361630 ->13643B0 consumes onei32. Result is not a UI gate:
    # no invented unavailable reply can substitute for committed own state.
    return Event(0x201,kind=0xd2b,payload=bytes(4))
