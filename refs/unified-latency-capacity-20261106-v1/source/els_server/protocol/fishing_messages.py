"""Exact current fishing wire inputs; no economic defaults or settlement scheduler.

2491180/24929E0 send empty8B4/8B6. 2491860 consumes8B8;
2BDE320 reads u32 count then u64 instance/i32 remaining values.
DD46E0 inventory records reuse the existing original move serializer.
BA9A20 reads8B3 current life stamina and the show-delta bool.
"""
import struct
from els_server.protocol.protocol_codec import Event


def _i32(value,label):
    if type(value)is not int or not -2**31<=value<2**31:
        raise ValueError(label)
    return value


def empty_request(payload):
    if type(payload)is not bytes or payload:
        raise ValueError('Native fishing start/stop payload must be empty')


def state_ack(result,*,stopped=False):
    if type(stopped)is not bool:raise ValueError('Fishing stop discriminator')
    return Event(0x201,kind=0x8b7 if stopped else 0x8b5,
                 payload=struct.pack('>i',_i32(result,'Fishing result bound')))


def life_snapshot(state):
    # Required explicit saved values. Missing state is handled by the caller
    # by retaining original fixture fields, never by assigning a life budget.
    if type(state)is not dict or set(state)!={'current','maximum'}:
        raise ValueError('Explicit life stamina snapshot required')
    current=_i32(state['current'],'Life current bound')
    maximum=_i32(state['maximum'],'Life maximum bound')
    if not 0<=current<=maximum:raise ValueError('Life current/maximum order')
    return {'0x510':struct.pack('>i',maximum),'0x514':struct.pack('>i',current)}


def life_notice(current,*,show_delta):
    current=_i32(current,'Life current bound')
    if current<0 or type(show_delta)is not bool:raise ValueError('Life notice bounds')
    return Event(0x201,kind=0x8b3,payload=struct.pack('>i?',current,show_delta))


def attempt_notice(result,*,caught,consumed=(),changes=()):
    # A notice encodes already-authoritative post-transaction values. It does
    # not accept a client attempt, draw, debit, grant or advance a quest.
    result=_i32(result,'Fishing result bound')
    if type(caught)is not bool:raise ValueError('Fishing caught flag')
    consumed=tuple(consumed);changes=tuple(changes)
    if len(consumed)>=2**32 or len(changes)>=2**32:raise ValueError('Fishing vector bound')
    if result!=0 and(caught or consumed or changes):
        raise ValueError('Rejected fishing notice cannot carry economic updates')
    seen=set();used=[]
    for pair in consumed:
        if type(pair)not in(tuple,list)or len(pair)!=2:raise ValueError('Fishing consumed row')
        uid,remaining=pair
        if type(uid)is not int or not 1<=uid<2**63 or uid in seen:
            raise ValueError('Fishing consumed instance identity')
        remaining=_i32(remaining,'Fishing remaining bound')
        if remaining<0:raise ValueError('Fishing remaining value cannot be negative')
        seen.add(uid);used.append(struct.pack('>Qi',uid,remaining))
    # Native DD46E0 is exactly the already-qualified inventory-vector shape.
    from els_server.domain.fashion_state import move_ack
    updates=move_ack(changes)[:-4]
    payload=struct.pack('>i?I',result,caught,len(used))+b''.join(used)+updates
    return Event(0x201,kind=0x8b8,payload=payload)
