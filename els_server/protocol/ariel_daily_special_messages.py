"""Original861 full normal map;27-byte rows follow the verified native reader."""
import struct
from els_server.protocol.protocol_codec import Event

def notification(rows,moment):
    if type(moment)is not int or not 0<=moment<2**40 or type(rows)is not tuple or len(rows)!=20:raise ValueError('Normal daily complete snapshot')
    data=struct.pack('>I',len(rows));previous=0
    for row in rows:
        if(type(row)is not tuple or len(row)!=3 or any(type(v)is not int for v in row)):raise ValueError('Normal daily row types')
        dungeon,used,maximum=row
        if not previous<dungeon<2**31 or maximum not in(1,2)or not 0<=used<=maximum:raise ValueError('Normal daily count boundary')
        previous=dungeon
        # Native ctor defaults1/false/current time64/false/false; normal
        # builder admits discriminator0. FieldD is not a reset deadline.
        data+=struct.pack('>iI',dungeon,1)+struct.pack('>iii?qi??',1,used,maximum,False,moment,0,False,False)
    return Event(0x201,kind=0x861,payload=data)
