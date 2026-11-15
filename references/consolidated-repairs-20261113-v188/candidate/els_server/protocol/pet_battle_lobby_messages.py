"""Original invited lobby136/139, A70/A71/A72 readiness and A73/A74 start."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.pet_battle_messages import pets

def selection(payload,*,allow_empty=False):
    # 30127A0/3012E20 ->30A7EF0 ->30ABF40 ->2BDE710: Q,u8 pairs.
    if type(payload)is not bytes or len(payload)<4:raise ValueError('Pet lobby selection length')
    count=struct.unpack_from('>I',payload)[0]
    if count not in((0,3)if allow_empty else(3,))or len(payload)!=4+9*count:raise ValueError('Pet lobby three selected pets')
    rows=tuple(struct.unpack_from('>QB',payload,4+9*i)for i in range(count))
    if len({uid for uid,ability in rows})!=count or any(not 0<uid<2**63 or ability not in(0,1,2,3,255)for uid,ability in rows):raise ValueError('Pet lobby owned selection shape')
    return tuple((uid,-1 if ability==255 else ability)for uid,ability in rows)

def ready_ack(rows=(),result=0):
    # 3010260 A71: original i32 then DC6880 vector, pending gate A71.
    return Event(0x201,kind=0xa71,payload=struct.pack('>i',(221) if result == -1 else result)+pets(rows))

def ready_notice(owner,rows=()):
    # 3010260 A72: original u64 then DC6880 vector.
    return Event(0x201,kind=0xa72,payload=struct.pack('>Q',owner)+pets(rows))

def start_ack(result=0):return Event(0x201,kind=0xa74,payload=struct.pack('>i',(223) if result == -1 else result))
