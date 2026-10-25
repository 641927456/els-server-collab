"""Current58C request/58D response fields recovered from original consumers."""
import struct
from els_server.protocol.protocol_codec import Event

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=7:raise ValueError('Town warp request length')
    destination,free,special,growth=struct.unpack('>i3B',payload)
    if any(v not in (0,1) for v in (free,special,growth)):raise ValueError('Town warp flags')
    if special or growth:raise ValueError('Special town warp context not qualified')
    return destination,free,special,growth

# Native79B330: -1 maps to an empty string;1355 is "ED不足。".
# Both codes are ordinary failures in the original751120 caller of58D.
GENERAL_FAILURE = 1
INSUFFICIENT_ED = 1355

def failure_code(reason):
    return INSUFFICIENT_ED if reason in ('Town warp insufficient ED','Village1012 insufficient ED') else GENERAL_FAILURE

def acknowledgement(destination,ed,*,result=0,details=(0,0,0,0)):
    if type(destination) is not int or not -2**31<=destination<2**31 or type(ed) is not int or not 0<=ed<2**63:raise ValueError('Town warp response values')
    if type(result)is not int or not -2**31<=result<2**31:
        raise ValueError('Town warp result range')
    if not isinstance(details,tuple)or len(details)!=4 or any(type(v)is not int or not 0<=v<2**31 for v in details):
        raise ValueError('Town warp conditional details')
    if result!=653 and any(details):raise ValueError('Town warp details require native653')
    # Original31305C0 only reads these conditional fields for result0x28D.
    return Event(0x201,kind=0x58d,payload=struct.pack('>iqi4i',result,ed,destination,*details))
