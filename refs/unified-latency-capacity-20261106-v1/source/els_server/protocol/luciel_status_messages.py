"""dx11_260923 native38E: DE1010/DB1910/DB1A20 and C5FF70.

Provider1A4ED30 writes DTO72 from the current SUnit2F50. Five ordered native
containers precede that byte; a fixed payload offset would be incorrect.
"""
import struct


def request(payload):
    if type(payload) is not bytes or not 62<=len(payload)<=65536:
        raise ValueError('LuCiel status size')
    # Five DWORDs, two bytes, one DWORD. They are unrelated status fields.
    offset=26
    for width in (8,8,4,8,8):
        if offset+4>len(payload):raise ValueError('LuCiel status count')
        count=struct.unpack_from('>I',payload,offset)[0];offset+=4
        if count>(len(payload)-offset)//width:raise ValueError('LuCiel status container bound')
        previous=None
        for index in range(count):
            key=struct.unpack_from('>i',payload,offset+index*width)[0]
            if previous is not None and key<=previous:raise ValueError('LuCiel status native ordering')
            previous=key
        offset+=count*width
    # DTO6A,6E DWORDs;72,73 bytes;74 WORD; sender's extra76 DWORD.
    if offset+16!=len(payload):raise ValueError('LuCiel status trailing data')
    active=payload[offset+8]
    if active not in (0,1):raise ValueError('LuCiel status active')
    return active
