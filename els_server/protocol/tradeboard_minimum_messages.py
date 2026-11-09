"""Exact A18/A19 active-offer minimum-list codec, not purchase history.

Auxiliary/pet/mount values preserve original i32 widths. Parsing does not
qualify their semantics; the provider must refuse any unbound values. The
third response i32 is opaque and defaults to zero, not an invented count.
"""
from dataclasses import dataclass
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.tradeboard_query_messages import listing


def _i32(value):
    if type(value) is not int or not -2**31 <= value < 2**31:
        raise ValueError('Exact native i32 required')
    return value


@dataclass(frozen=True)
class Request:
    template: int
    auxiliary: int
    pet_data_id: int
    mount_data_id: int

    def __post_init__(self):
        for value in (self.template,self.auxiliary,self.pet_data_id,self.mount_data_id):
            _i32(value)
        if self.template <= 0:
            raise ValueError('Positive native template required')


def request(payload):
    if type(payload) is not bytes or len(payload) != 16:
        raise ValueError('A18 requires exactly four native i32 values')
    return Request(*struct.unpack('>iiii',payload))


def reply(template, rows=(), *, result=0, opaque=0):
    _i32(template);_i32(result);_i32(opaque)
    if template < 0 or (result == 0 and template == 0):
        raise ValueError('Native reply template identity')
    if type(rows) not in (tuple,list):
        raise ValueError('Explicit authoritative listing sequence required')
    if result and rows:
        raise ValueError('Rejected A19 has no successful listings')
    seen=set();parts=[]
    for row in rows:
        raw=listing(row)  # The qualified complete44D serializer and full item.
        if row['item']['template'] != template:
            raise ValueError('A19 listings must match the requested template')
        identity=row['listing_id']
        if identity in seen:
            raise ValueError('Duplicate native listing identity')
        seen.add(identity);parts.append(raw)
    payload=struct.pack('>iiiI',result,template,opaque,len(parts))+b''.join(parts)
    if len(payload)+64 > 1024*1024:
        raise ValueError('Native secure-frame response bound')
    return Event(0x201,kind=0xa19,payload=payload)
