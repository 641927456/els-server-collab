"""Original DA5110/DA5310 preset summaries and D37/D38 payloads."""
from els_server.protocol.housing_layout_messages import encode,decode
from els_server.protocol.protocol_codec import Event
import struct

LEGACY=('vec',('tuple','i','i','i','i'))
MODERN=('vec',('tuple','i','i','i',('tuple','f','f','f'),'i'))
PRESET=('tuple','i','str','i',LEGACY,MODERN)
REQUEST=('tuple',PRESET,'bool')

def request(payload):return decode(REQUEST,payload)

def acknowledgement(preset,*,result=0):
 return Event(0x201,kind=0xd38,payload=struct.pack('>i',result)+encode(PRESET,preset))
