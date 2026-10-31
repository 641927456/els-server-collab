"""Current8C1/3/5 requests and8C0/2/4/6 payloads; no economic defaults.

2BE74B0 writes twoi32 then u32/u64 pet IDs for8C1. 10FEEF0
writes twoi32 for8C3/5. 2BE19A0 reads twoi32, DB27F0→DD1990
pet records, two u64 times. Pet records reuse qualified D9C550;
completion inventory uses original DD46E0. Field names reflect DTO
positions; the opaque auxiliary response integer is required explicitly.
"""
import struct
from els_server.protocol.protocol_codec import Event


def _i32(value):
    if type(value) is not int or not -2**31<=value<2**31:
        raise ValueError('Expedition signed32 bound')
    return value


def _uid(value,zero=False):
    if type(value) is not int or not (0 if zero else 1)<=value<2**63:
        raise ValueError('Expedition UID/time bound')
    return value


def request(kind,payload):
    if type(payload) is not bytes or kind not in (0x8c1,0x8c3,0x8c5):
        raise ValueError('Expedition request kind/payload')
    if len(payload)<8:raise ValueError('Expedition request truncated')
    key,mission=struct.unpack_from('>ii',payload)
    if key<=0 or mission<=0:raise ValueError('Expedition original mission identity')
    if kind!=0x8c1:
        if len(payload)!=8:raise ValueError('Expedition complete/cancel request length')
        return key,mission,()
    if len(payload)<12:raise ValueError('Expedition start truncated')
    count=struct.unpack_from('>I',payload,8)[0]
    if not 1<=count<=3 or len(payload)!=12+8*count:
        raise ValueError('Expedition selected pet vector bound')
    pets=tuple(struct.unpack_from('>Q',payload,12+8*n)[0] for n in range(count))
    if len(set(pets))!=count:raise ValueError('Expedition repeated pet')
    for pet in pets:_uid(pet)
    return key,mission,pets


def _pet_vector(pets):
    from els_server.protocol.companion_messages import pet_record
    pets=tuple(pets)
    if len(pets)>3:raise ValueError('Expedition pet record bound')
    ids=[]
    for pet in pets:
        if type(pet) is not dict:raise ValueError('Expedition explicit saved pet required')
        ids.append(_uid(pet['uid']))
        if type(pet['unit']) is not int or pet['unit']<=0:raise ValueError('Expedition original pet unit')
    if len(set(ids))!=len(ids):raise ValueError('Expedition duplicate saved pet')
    return struct.pack('>I',len(pets))+b''.join(pet_record(pet) for pet in pets)


def board_record(*,mission,region,pets,started_at,ends_at):
    mission=_i32(mission);region=_i32(region)
    if mission<=0 or region<=0:raise ValueError('Expedition board original identities')
    started_at=_uid(started_at,True);ends_at=_uid(ends_at,True)
    if started_at>ends_at:raise ValueError('Expedition board time order')
    return struct.pack('>ii',mission,region)+_pet_vector(pets)+struct.pack('>QQ',started_at,ends_at)


def board_notice(rows):
    if type(rows) is not dict or len(rows)>9:raise ValueError('Expedition board finite scope')
    data=[]
    for key,row in sorted(rows.items()):
        if _i32(key)<=0:raise ValueError('Expedition board key')
        data.append(struct.pack('>i',key)+board_record(**row))
    return Event(0x201,kind=0x8c0,payload=struct.pack('>I',len(rows))+b''.join(data))


def state_ack(kind,*,result,native_auxiliary,ed,state):
    if kind not in (0x8c2,0x8c6):raise ValueError('Expedition state acknowledgement kind')
    # 2B57C30 has twoi32 before ED. Auxiliary semantics are not inferred.
    return Event(0x201,kind=kind,payload=struct.pack('>iiQ',_i32(result),_i32(native_auxiliary),_uid(ed,True))+board_record(**state))


def completion_ack(*,result,state,rewards,changes):
    from els_server.domain.inventory_items import inventory_payload
    if type(rewards) is not dict:raise ValueError('Explicit expedition reward map required')
    pairs=[]
    for template,quantity in sorted(rewards.items()):
        if _i32(template)<=0 or _i32(quantity)<=0:raise ValueError('Expedition reward map bounds')
        pairs.append(struct.pack('>ii',template,quantity))
    data=struct.pack('>i',_i32(result))+board_record(**state)
    data+=struct.pack('>I',len(pairs))+b''.join(pairs)+inventory_payload(list(changes))
    return Event(0x201,kind=0x8c4,payload=data)
