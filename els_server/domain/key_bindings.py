"""Three native maps<signed short,signed short>, CDDE60/CDDD40."""
import struct
DEFAULT_BINDINGS=bytes(12)

def validate_bindings(payload):
    offset=0
    for map_index in range(3):
        if offset+4>len(payload):raise ValueError('Truncated key map count')
        count=struct.unpack_from('>I',payload,offset)[0];offset+=4
        if count>256 or offset+count*4>len(payload):raise ValueError('Invalid key map size')
        seen=set()
        for i in range(count):
            key,value=struct.unpack_from('>hh',payload,offset+i*4)
            # Native keyboard action table has 85 entries. -1 is the native
            # disabled sentinel (observed for eight reserved actions); codes
            # 81..164 also represent disabled actions. Other maps use byte codes.
            if not 0<=key<85 or not -1<=value<=(164 if map_index==0 else 255):
                raise ValueError('Unsupported key binding index')
            if key in seen:raise ValueError('Duplicate key map index')
            seen.add(key)
        offset+=count*4
    if offset!=len(payload):raise ValueError('Trailing key binding data')
    return bytes(payload)
