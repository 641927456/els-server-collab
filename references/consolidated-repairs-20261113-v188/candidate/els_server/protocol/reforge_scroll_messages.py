"""Original2353480 two-UID A22 writer and2271550 A23 inventory consumer."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.equipment_reforge_messages import changes_wire

def request(payload):
    if type(payload)is not bytes or len(payload)!=16:raise ValueError('Reforge scroll request size')
    target,source=struct.unpack('>QQ',payload)
    if not 0<target<2**63 or not 0<source<2**63 or target==source:raise ValueError('Reforge scroll identities')
    return target,source

def acknowledgement(changes=(),result=0):
    return Event(0x201,kind=0xa23,payload=struct.pack('>i',(500) if result in (-1, 2005) else result)+changes_wire(changes))
