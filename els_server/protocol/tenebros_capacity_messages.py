"""Native 9F1/9F2/9F3 capacity projection; no shadow-option operations."""
import struct
from els_server.protocol.protocol_codec import Event


def integer(value,low,high):
    if type(value) is not int or not low<=value<=high:raise ValueError('Tenebros wire integer')
    return value


def request(payload):
    if type(payload) is not bytes or len(payload)!=4:raise ValueError('Tenebros request length')
    return integer(struct.unpack('>i',payload)[0],0,3)


def capacities(extras):
    if type(extras) not in (tuple,list) or len(extras)!=4:raise ValueError('Tenebros four parts')
    return tuple(integer(v,0,3) for v in extras)


def row(extra, options=None):
    if options is not None:
        from els_server.protocol.tenebros_storage_messages import storage_row
        return storage_row(extra,options)
    # Current native missing-part initializer allocates six zero option IDs.
    # This capacity-only server has no shadow-option deposit/withdraw writer.
    return struct.pack('>iI6i',integer(extra,0,3),6,0,0,0,0,0,0)


def state(extras):
    return Event(0x201,kind=0x9f1,payload=struct.pack('>I',4)+b''.join(
        struct.pack('>i',part)+row(extra) for part,extra in enumerate(capacities(extras))))


def acknowledge(part=0,extra=0,ed=0,*,result=0,options=None):
    return Event(0x201,kind=0x9f3,payload=struct.pack('>iQi',
        integer(result,-2**31,2**31-1),integer(ed,0,2**63-1),integer(part,0,3))+row(extra,options))
