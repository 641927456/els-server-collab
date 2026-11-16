"""Original861 complete map: normal daily and Mirror weekly providers."""
import struct
from els_server.protocol.protocol_codec import Event

def notification(rows,moment,*,mirror_remaining):
    if type(mirror_remaining)is not int or not 0<=mirror_remaining<=5:raise ValueError('Mirror weekly count bounds')
    if type(moment)is not int or not 0<=moment<2**40 or type(rows)is not tuple or len(rows)!=20:raise ValueError('Normal daily complete snapshot')
    data=struct.pack('>I',len(rows)+1);previous=0
    for row in rows:
        if(type(row)is not tuple or len(row)!=3 or any(type(v)is not int for v in row)):raise ValueError('Normal daily row types')
        dungeon,used,maximum=row
        if not previous<dungeon<2**31 or maximum not in(1,2)or not 0<=used<=maximum:raise ValueError('Normal daily count boundary')
        previous=dungeon
        # Native ctor defaults1/false/current time64/false/false; normal
        # builder admits discriminator0. FieldD is not a reset deadline.
        data+=struct.pack('>iI',dungeon,1)+struct.pack('>iii?qi??',1,used,maximum,False,moment,0,False,False)
    if any(r[0]==35860 for r in rows):raise ValueError('Weekly provider key collision')
    # Keep both providers: the native reader replaces this whole map. The
    # Mirror time field stays its verified opaque compatibility zero.
    data+=struct.pack('>iIiii?qi??',35860,1,1,5-mirror_remaining,5,False,0,19,False,False)
    return Event(0x201,kind=0x861,payload=data)
