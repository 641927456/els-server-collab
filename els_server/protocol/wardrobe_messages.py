"""Native2351E10/2352170 writers;226BF50/226C9C0 and13890C0 readers."""
import struct
from els_server.protocol.protocol_codec import Event


def register_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=8:raise ValueError('Wardrobe register payload')
    uid=struct.unpack('>Q',payload)[0]
    if not 0<uid<2**63:raise ValueError('Wardrobe item UID')
    return uid


def apply_request(payload):
    # map<int,{int template,Q targetUID,array<int,3>}>. Tags are implicit.
    if not isinstance(payload,bytes) or len(payload)<4:raise ValueError('Wardrobe apply payload')
    count=struct.unpack_from('>I',payload)[0]
    if not 1<=count<=32 or len(payload)!=4+32*count:raise ValueError('Wardrobe apply count/size')
    rows=[];keys=set();uids=set()
    for n in range(count):
        position,template,uid,size,a,b,c=struct.unpack_from('>iiQIiii',payload,4+32*n)
        if position in keys or uid in uids or size!=3 or (a,b,c)!=(0,0,0) or not 0<uid<2**63 or template<=0:
            raise ValueError('Wardrobe duplicate, dye or invalid fields')
        keys.add(position);uids.add(uid);rows.append((position,template,uid))
    return rows


def registry_wire(counts):
    if len(counts)>72885 or any(type(k)is not int or not 0<k<2**31 or type(v)is not int or not 1<=v<2**31 for k,v in counts.items()):
        raise ValueError('Wardrobe registry bounds')
    return struct.pack('>I',len(counts))+b''.join(struct.pack('>ii',k,v)for k,v in sorted(counts.items()))


def initialization(counts):
    # 31 installs manager+338 (registered appearance counts), then empty favorites.
    return Event(0x201,kind=0x31,payload=bytes(4)+registry_wire(counts)+bytes(4))


def acknowledgement(kind,counts=None,changes=(),result=0):
    from els_server.domain.fashion_state import move_ack
    if kind not in (0x4af,0x4b1):raise ValueError('Wardrobe operation kind')
    # Both readers consume result, map<int,int>, then DD46E0 inventory vector.
    return Event(0x201,kind=kind+1,payload=struct.pack('>i',result)+registry_wire(counts or {})+move_ack(changes)[:-4])
