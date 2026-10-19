"""A69 empty request, A6A empty admitted catalogue/rates, A5C/A5D conversion."""
import struct
from els_server.domain.ep_points import validate
from els_server.domain.ep_conversion import Rate,ConversionResult,ConversionRejected
from els_server.protocol.protocol_codec import Event

def request(payload):
    if type(payload) is not bytes or len(payload)!=4:
        raise ConversionRejected(ConversionResult.UNKNOWN)
    quantity,=struct.unpack('>i',payload)
    if quantity<=0:raise ConversionRejected(ConversionResult.UNKNOWN)
    return quantity

def _result(result):
    if type(result) is not int or result not in (0,*map(int,ConversionResult)):
        raise ValueError('Unqualified EP result code')
    return result

def acknowledgement(ed,ep,result=0):
    if type(ed) is not int or not 0<=ed<2**63:raise ValueError('Invalid saved ED balance')
    validate(ep)
    return Event(0x201,kind=0xa5d,payload=struct.pack('>iQQ',_result(result),ed,ep))

def catalogue(rate=None,result=0):
    result=_result(result)
    if result==0 and type(rate) is not Rate:raise ValueError('Missing admitted EP rate')
    ed,ep=(rate.ed_per_bundle,rate.ep_per_bundle) if result==0 else (0,0)
    # No retail SKU is admitted. The original reader accepts an empty map;
    # advertise only the independently source-qualified conversion units.
    return Event(0x201,kind=0xa6a,payload=struct.pack('>iiQQ',result,0,ed,ep))
