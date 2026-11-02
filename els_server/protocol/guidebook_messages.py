"""DX11 9631C0/2BE0D90 upload and BDA930/2BE0EA0 restore readers."""
import struct
from els_server.protocol.protocol_codec import Event


def request(payload):
    if len(payload)<4:raise ValueError('Truncated guidebook flags')
    count=struct.unpack_from('>I',payload)[0]
    body=payload[4:]
    # The native upload's count field can lag its entry vector: the fixed
    # DX11 capture sends a five-entry body behind a four-entry header. Never
    # admit a body shorter than the header promises, but read every entry the
    # bytes actually carry and validate all of them.
    if len(body)%5 or len(body)<5*count:raise ValueError('Guidebook flags size %d/%d'%(len(body),count))
    flags={}
    for index,opened in struct.iter_unpack('>iB',body):
        if index<=0 or opened not in (0,1) or index in flags:
            raise ValueError('Invalid guidebook flag')
        flags[index]=opened
    return flags


def initialization(flags):
    payload=struct.pack('>iI',0,len(flags))
    payload+=b''.join(struct.pack('>iB',index,opened) for index,opened in sorted(flags.items()))
    return Event(0x201,kind=0x811,payload=payload)
