"""Current A11/A12 saved-condition wire codec, without owner storage or dispatch.

CC is a distinct packed record, not an embedded A0A/A0C filter DTO. Offset
names deliberately preserve unqualified semantics. Its first Q is the native
tree key, compared as signed int64 by original 2C34F40.
"""
from dataclasses import dataclass
import struct
from els_server.protocol.protocol_codec import Event

LAYOUT = (
    ('key_00','i64'),('byte_08','u8'),('text_09','text'),('text_29','text'),
    ('flag_49','bool'),('byte_4a','u8'),('byte_4b','u8'),
    ('bits_4c','u64'),('bits_54','u64'),('bits_5c','u64'),
    ('bits_64','u64'),('bits_6c','u64'),
    ('byte_74','u8'),('byte_75','u8'),('byte_76','u8'),('byte_77','u8'),
    ('ids_78','vector'),('ids_90','vector'),('value_a8','u64'),('value_b0','u64'),
    ('value_b8','i32'),('value_bc','i32'),('value_c0','i32'),
    ('value_c4','i32'),('value_c8','i32'),
)
FORMATS={'i64':'q','u64':'Q','i32':'i','u8':'B'}
MAX_RECORDS=20
MAX_TEXT_BYTES=4096  # Defensive server bound, not claimed as native UI label limit.
MAX_BODY=1024*1024-64

@dataclass(frozen=True)
class Request:
    tag: int
    record: dict

def scalar(kind,value):
    if type(value) is not int:raise ValueError('Exact integer required')
    try:return struct.pack('>'+FORMATS[kind],value)
    except (struct.error,KeyError) as e:raise ValueError('Integer width') from e

def record(value):
    if type(value) is not dict or set(value)!={name for name,_ in LAYOUT}:
        raise ValueError('Exact CC field set required')
    parts=[]
    for name,kind in LAYOUT:
        field=value[name]
        if kind in FORMATS:raw=scalar(kind,field)
        elif kind=='bool':
            if type(field) is not bool:raise ValueError('Canonical boolean required')
            raw=bytes((int(field),))
        elif kind=='text':
            if type(field) is not str or '\0' in field:raise ValueError('UTF16 text required')
            try:encoded=field.encode('utf-16le')
            except UnicodeError as e:raise ValueError('Invalid UTF16') from e
            if len(encoded)>MAX_TEXT_BYTES:raise ValueError('Text defensive bound')
            raw=struct.pack('>I',len(encoded))+encoded
        else:
            if type(field) not in (tuple,list) or len(field)>MAX_BODY//4:
                raise ValueError('Finite i32 vector required')
            raw=struct.pack('>I',len(field))+b''.join(scalar('i32',x) for x in field)
        parts.append(raw)
    raw=b''.join(parts)
    if len(raw)>MAX_BODY:raise ValueError('Native frame bound')
    return raw

class Reader:
    def __init__(self,payload):
        if type(payload) is not bytes or len(payload)>MAX_BODY:raise ValueError('Finite bytes required')
        self.payload=payload;self.pos=0
    def take(self,n):
        if n>len(self.payload)-self.pos:raise ValueError('Truncated favorite record')
        out=self.payload[self.pos:self.pos+n];self.pos+=n;return out
    def number(self,fmt):return struct.unpack('>'+fmt,self.take(struct.calcsize('>'+fmt)))[0]
    def cc(self):
        out={}
        for name,kind in LAYOUT:
            if kind in FORMATS:value=self.number(FORMATS[kind])
            elif kind=='bool':
                value=self.number('B')
                if value not in (0,1):raise ValueError('Noncanonical bool')
                value=bool(value)
            elif kind=='text':
                n=self.number('I')
                if n>MAX_TEXT_BYTES or n%2:raise ValueError('UTF16 byte length')
                try:value=self.take(n).decode('utf-16le')
                except UnicodeError as e:raise ValueError('Invalid UTF16') from e
                if '\0' in value:raise ValueError('Embedded NUL')
            else:
                n=self.number('I')
                if n>(len(self.payload)-self.pos)//4:raise ValueError('Vector count exceeds body')
                value=tuple(self.number('i') for _ in range(n))
            out[name]=value
        return out

def request(payload):
    r=Reader(payload);tag=r.number('B');value=r.cc()
    if r.pos!=len(payload):raise ValueError('Trailing A11 bytes')
    return Request(tag,value)

def request_body(value):
    if type(value) is not Request:raise ValueError('Typed request required')
    raw=scalar('u8',value.tag)+record(value.record)
    if len(raw)>MAX_BODY:raise ValueError('Native frame bound')
    return raw

def reply(rows=(),*,result=0,flag=False):
    status=scalar('i32',result)
    if type(flag) is not bool or type(rows) not in(tuple,list) or len(rows)>MAX_RECORDS:
        raise ValueError('Favorite reply inputs')
    if result and(rows or flag):raise ValueError('Rejected reply has no rows/flag')
    parts=[];previous=None
    for row in rows:
        raw=record(row);key=row['key_00']
        if previous is not None and key<=previous:raise ValueError('Unique signed-key order required')
        previous=key;parts.append(raw)
    payload=status+bytes((int(flag),))+struct.pack('>I',len(parts))+b''.join(parts)
    if len(payload)>MAX_BODY:raise ValueError('Native frame bound')
    return Event(0x201,kind=0xa12,payload=payload)
