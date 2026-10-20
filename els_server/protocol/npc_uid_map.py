"""UID translation data for the pinned DX11 native begin-substage consumer.

1044D70 -> 1076D70 -> 1AEB4C0 decodes the BD vector into Game+1060's Lua table.
The native death caller converts its entry with the CRC lookup and template
salt below. Empty input otherwise turns a missing entry into death UID zero.
The discarded B2 serializer string is left unchanged.
Only wire preparation lives here; native creation, death and clear logic stay
in the client, and existing server instance/phase/retry validation stays intact.
"""
import struct,zlib

def _crc_entry(value):
    for _ in range(8):value=(value>>1)^(0xedb88320 if value&1 else 0)
    return value

_CRC=tuple(_crc_entry(i) for i in range(256))
_LOW={word&255:index for index,word in enumerate(_CRC)}
assert len(_LOW)==256

def uid_translation_vector(entries):
    entries=tuple(entries)
    if len(entries)>16384:raise ValueError('Static NPC UID count')
    seen=set();words=[]
    for uid,template in entries:
        if type(uid) is not int or not 0<=uid<2**31 or uid in seen:raise ValueError('Static NPC UID identity')
        if type(template) is not int or not 0<template<2**31:raise ValueError('Static NPC template identity')
        seen.add(uid)
        # The native checksum also XORs the actor UID. Encoding its
        # template guard preserves that UID; encoding the UID again cancels it.
        target=template^0x1f6781a2
        low=_LOW[target&255]
        words.append(((target^_CRC[low])&0xffffff00)|low)
    if not words:return bytes(4)
    compressed=zlib.compress(struct.pack('<'+'I'*len(words),*words))
    key=bytes.fromhex('d4b5bd32')
    encoded=bytes(value^key[index%4] for index,value in enumerate(compressed))
    return struct.pack('>I',len(encoded))+encoded
