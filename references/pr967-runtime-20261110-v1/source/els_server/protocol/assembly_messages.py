"""Original Type2 purchase911 and result/ED912, pinned2BEA8E0/B7C170."""
import struct
from els_server.protocol.protocol_codec import Event

def request(payload):
    if not isinstance(payload,bytes)or payload!=struct.pack('>i',2):raise ValueError('Assembly native SpaType request')
    return 2

def acknowledgement(ed,result=0):
    if type(ed)is not int or not 0<=ed<2**63 or result not in(0,-1):raise ValueError('Assembly purchase response')
    return Event(0x201,kind=0x912,payload=struct.pack('>iQ',result,ed))
