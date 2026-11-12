"""Original DB3070/DB2F80 ten-byte preferences, 2F and167/168."""
import struct
from els_server.protocol.protocol_codec import Event

# Existing unsaved fields retain zero. Enable the previously unconnected
# mentor invitation flag; an explicit native167 save owns all ten choices.
DEFAULT=bytes((0,0,0,0,0,0,0,1,0,0))
MENTOR_INVITATIONS=7

def validate(payload):
    if type(payload)is not bytes or len(payload)!=10 or any(value>1 for value in payload):
        raise ValueError('Native social settings require ten booleans')
    return payload

def reply(payload,result=0):
    return Event(0x201,kind=0x168,payload=struct.pack('>i',result)+validate(payload))
