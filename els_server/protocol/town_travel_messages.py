"""Current58C request/58D response fields recovered from original consumers."""
import struct
from els_server.protocol.protocol_codec import Event

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=7:raise ValueError('Town warp request length')
    destination,free,special,growth=struct.unpack('>i3B',payload)
    if any(v not in (0,1) for v in (free,special,growth)):raise ValueError('Town warp flags')
    if special or growth:raise ValueError('Special town warp context not qualified')
    return destination,free,special,growth

def acknowledgement(destination,ed,*,result=0):
    if type(destination) is not int or not -2**31<=destination<2**31 or type(ed) is not int or not 0<=ed<2**63:raise ValueError('Town warp response values')
    # Four conditional error-detail fields are unused on success.
    return Event(0x201,kind=0x58d,payload=struct.pack('>iqi4i',result,ed,destination,0,0,0,0))
