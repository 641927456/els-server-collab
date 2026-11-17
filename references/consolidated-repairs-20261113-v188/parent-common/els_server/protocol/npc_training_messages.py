"""Original free training 18F request and 190 selected member acknowledgement."""
import struct
from els_server.protocol.dungeon_messages import member
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event

TRAINING_TEMPLATE=1
TRAINING_DUNGEON=39000


def acknowledgement(character,slots,items,port,*,result=0):
    # 21B68D0 -> 215DBC0/31BC950 build a type-3 native training room.
    # The actual player's member uses the same D9D2F0 reader as solo dungeons.
    prefix=struct.pack('>iiiQB',result,TRAINING_TEMPLATE,TRAINING_DUNGEON,character['uid'],0)
    endpoint=wstring('127.0.0.1')+struct.pack('>H',port)+wstring('')+struct.pack('>f',0.0)
    return Event(0x201,kind=0x190,payload=prefix+endpoint+member(slots,character,items)+bytes(8))
