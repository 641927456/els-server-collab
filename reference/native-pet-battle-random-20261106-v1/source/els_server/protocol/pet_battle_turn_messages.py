"""Current A6B turn records, using the original native nested DTO readers.

Caller owns admission, actor binding, combat resolution and reward authority.
Fields107..113 are action, display style, attack outcome and displayed amount.
32A7A00 consumes11F as HP;32A7CE0 consumes12F as enchant turns.
The unused member bool retains zero.2B1BB60 consumes13F as the other active pet UID.
"""
import struct
from els_server.protocol.protocol_codec import Event


def _vector(records):
    records=tuple(records)
    return struct.pack('>I',len(records))+b''.join(records)


def _values(values):
    return _vector(struct.pack('>Qi',uid,value)for uid,value in sorted(values.items()))


def member(owner,full_user,pet_vector,planned,active,defence_left):
    """2C2A0B0: FullUser, three pets, planned actions and current active UID.

The final i32 is remaining defence uses, not action-slot count:300D510
passes it to slot1 (DEFENCE), while slot3 (HEAL) starts at1 each round.
"""
    actions=_vector(struct.pack('>iQ',kind,target)for kind,target in planned)
    return (struct.pack('>Q',owner)+full_user+pet_vector+actions
        +struct.pack('>Qi?',active,defence_left,False))


def action_result(pet_state,action,style,outcome,amount,target,hp,enchant,other_active):
    """2C2A550 stride147; styles/outcomes are supplied by the battle adapter."""
    return (pet_state+struct.pack('>iiiiQ',action,style,outcome,amount,target)
        +_values(hp)+_values(enchant)+struct.pack('>Q',other_active))


def turn(number,members,results=()):
    return Event(0x201,kind=0xa6b,payload=struct.pack('>i',number)
        +_vector(members)+_vector(results))
