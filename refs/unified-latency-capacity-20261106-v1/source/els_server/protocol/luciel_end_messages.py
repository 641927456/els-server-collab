"""Native67 end report; source1AB2B10/DC3B70/DA2F50 and nested maps.
Isolated protocol candidate; not yet wired to server lifecycle.
"""
import struct

def request(payload):
    if type(payload) is not bytes or not 190<=len(payload)<=8192:
        raise ValueError('LuCiel end-report size')
    if payload[:4]!=struct.pack('>I',0x72):raise ValueError('LuCiel end-report reason')
    offset=4
    def take(size):
        nonlocal offset
        if size>len(payload)-offset:raise ValueError('LuCiel end-report bound')
        result=payload[offset:offset+size];offset+=size;return result
    def count(minimum):
        value=struct.unpack('>I',take(4))[0]
        if value>(len(payload)-offset)//minimum:raise ValueError('LuCiel end-report count')
        return value
    def ordered(keyfmt,value_size,nested=False):
        previous=None
        size=struct.calcsize(keyfmt)
        for _ in range(count(size+(4 if nested else value_size))):
            key=struct.unpack(keyfmt,take(size))[0]
            if previous is not None and key<=previous:raise ValueError('LuCiel end-report order')
            previous=key
            if nested:ordered('>i',4)
            else:take(value_size)
    take(8);ordered('>i',4);take(20)
    for _ in range(8):ordered('>Q',4)
    take(16);ordered('>Q',4);take(32)
    take(1);take(16);active=take(1)[0]
    if active not in (0,1):raise ValueError('LuCiel end-report active')
    take(28)
    for _ in range(4):ordered('>Q',0,nested=True)
    ordered('>i',0);take(4)
    if offset!=len(payload):raise ValueError('LuCiel end-report trailing data')
    return active
