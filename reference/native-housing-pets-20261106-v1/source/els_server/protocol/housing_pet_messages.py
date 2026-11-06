"""Original A38/A39 and 924+1B4 layouts; no placement or reward authority."""
import struct
from els_server.protocol.companion_messages import pet_record
from els_server.protocol.protocol_codec import Event


def placement_request(payload):
    # 3287520 -> 332F6C0 -> 3336220: Byte slot, UInt64 selected pet.
    if type(payload)is not bytes or len(payload)!=9:
        raise ValueError('Housing pet placement request')
    return struct.unpack('>BQ',payload)


def placements(rows):
    # 2C27800: ordered byte key, byte, UInt64, then the existing D9C550 DTO.
    # The two auxiliary fields keep their native offsets until their actual
    # consumers establish semantics. This codec never synthesizes a date.
    if type(rows)is not list or len(rows)>256:
        raise ValueError('Housing pet placement container')
    if any(type(row)is not tuple or len(row)!=4 for row in rows):
        raise ValueError('Housing pet placement record')
    keys=[row[0]for row in rows]
    if any(type(key)is not int or not 0<=key<=255 for key in keys)or keys!=sorted(set(keys)):
        raise ValueError('Housing pet placement ordered byte keys')
    parts=[]
    for slot,byte_1,value_2,pet in rows:
        if(type(byte_1)is not int or not 0<=byte_1<=255
           or type(value_2)is not int or not 0<=value_2<2**64
           or type(pet)is not dict):
            raise ValueError('Housing pet placement native fields')
        parts.append(struct.pack('>BBQ',slot,byte_1,value_2)+pet_record(pet))
    raw=struct.pack('>I',len(rows))+b''.join(parts)
    if len(raw)>65536:
        raise ValueError('Housing pet placement payload bound')
    return raw


def placement_ack(result,rows,*,kind=0xa39):
    # 332F920 reads i32 result followed by this exact ordered container.
    if type(result)is not int or kind not in(0xa39,0xa3b):
        raise ValueError('Housing pet placement result')
    return Event(0x201,kind=kind,payload=struct.pack('>i',result)+placements(rows))


def placement_restore(rows):
    # B7C170/A37 -> BE64E0 restores the owner's off-scene placed-pet set.
    return Event(0x201,kind=0xa37,payload=placements(rows))
