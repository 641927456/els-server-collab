"""DX11 9631C0/2BE0D90 upload and BDA930/2BE0EA0 restore readers."""
import struct
from els_server.protocol.protocol_codec import Event


def request(payload):
    if len(payload)<4:raise ValueError('Truncated guidebook flags')
    count=struct.unpack_from('>I',payload)[0]
    if len(payload)!=4+5*count:raise ValueError('Guidebook flags size')
    flags={}
    for index,opened in struct.iter_unpack('>iB',payload[4:]):
        if index<=0 or opened not in (0,1) or index in flags:
            raise ValueError('Invalid guidebook flag')
        flags[index]=opened
    return flags


def initialization(flags):
    payload=struct.pack('>iI',0,len(flags))
    payload+=b''.join(struct.pack('>iB',index,opened) for index,opened in sorted(flags.items()))
    return Event(0x201,kind=0x811,payload=payload)
