"""9B3 empty request,9B4 big-endian37B,9B2 big-endian21B native state.

flag0/raw-u64(1FD)0 are local compatibility values, no inferred field names.
Deadline is Unix seconds, same as verified1F0 engine+4F0 clock, not FILETIME.
"""
import struct
from els_server.protocol.protocol_codec import Event
def state_wire(hammers=0,ready_at=0):
 if type(hammers)is not int or not 0<=hammers<=20:raise ValueError('Anvil hammer balance')
 if type(ready_at)is not int or not 0<=ready_at<2**63:raise ValueError('Anvil Unix deadline')
 return struct.pack('>BiQQ',0,hammers,0,ready_at)
def request(payload):
 if type(payload)is not bytes or payload:raise ValueError('Native9B3 requires empty body')
def acknowledgement(ed=0,hammers=0,ready_at=0,xp=0,result=0):
 if type(ed)is not int or not 0<=ed<2**63 or type(xp)is not int or not 0<=xp<2**31 or type(result)is not int or not -2**31<=result<2**31:raise ValueError('Anvil response range')
 return Event(0x201,kind=0x9b4,payload=struct.pack('>iQi',result,ed,xp)+state_wire(hammers,ready_at))
def notification(hammers=0,ready_at=0):
 return Event(0x201,kind=0x9b2,payload=state_wire(hammers,ready_at))
