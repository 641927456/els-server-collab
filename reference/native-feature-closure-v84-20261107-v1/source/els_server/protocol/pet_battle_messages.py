"""Pinned pet-fight wire contracts; admission, numbers and outcomes stay in flow.

2D668E0/3015200 produce342 mode(13,0,false) with three UID/ability
pairs. 3333E00/DB8560 produceA6C and32A1C20 reads its i32 A6D.
D9D2F0+5EC/DB2AD0/DC6880 read the same pet-state vector used by the
native PetFightRoom. HP and enchant turns are supplied by the caller.
"""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.companion_messages import pet_record
from els_server.protocol.pvp_match_messages import registration


def selection(payload):
    modes,hint,rows=registration(payload)
    if modes!=((13,0,False),)or len(rows)!=3:
        raise ValueError('Native pet-fight three-pet selection')
    selected=[]
    for uid,ability in rows:
        if ability==255:ability=-1
        if ability not in(-1,0,1,2,3):
            raise ValueError('Native pet-fight growth choice')
        selected.append((uid,ability))
    return hint,tuple(selected)


def actions(payload):
    """Three i32/UID actions followed by the currently selected pet UID."""
    if type(payload)is not bytes or len(payload)!=48:
        raise ValueError('Native pet-fight action body')
    count,*values=struct.unpack('>IiQiQiQQ',payload)
    if count!=3:
        raise ValueError('Native pet-fight three action slots')
    return tuple((values[i],values[i+1])for i in range(0,6,2)),values[6]


def action_ack(result):
    return Event(0x201,kind=0xa6d,payload=struct.pack('>i',result))


def pet_state(pet,ability,hp,enchant_turns):
    """DC6880 stride107: existing D9C550 DTO plus FB/FF/103 i32 fields."""
    if type(ability)is not int or ability not in(-1,0,1,2,3):
        raise ValueError('Native pet-fight growth choice')
    if any(type(value)is not int or value<0 for value in(hp,enchant_turns)):
        raise ValueError('Native pet-fight state integer')
    return pet_record(pet)+struct.pack('>iii',ability,hp,enchant_turns)


def pets(rows):
    rows=tuple(rows)
    if len(rows)>3:
        raise ValueError('Native pet-fight roster size')
    return struct.pack('>I',len(rows))+b''.join(pet_state(*row)for row in rows)
