"""Current AA1-AA3 and existing DA0840 fields; no client-side UI recreation."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol import social_messages as wire


def assignments(payload):
    if len(payload)<4:raise ValueError('Union map header')
    count=struct.unpack_from('>I',payload)[0]
    if not 2<=count<=8 or len(payload)!=4+13*count:raise ValueError('Union map size')
    result={};previous=-1
    for offset in range(4,len(payload),13):
        uid,group,leader=struct.unpack_from('>QiB',payload,offset)
        # Original2D41F90 traverses a UID-ordered map, not arbitrary slot data.
        if uid<=previous or group not in (0,1) or leader not in (0,1):raise ValueError('Union map entry')
        result[uid]=(group,bool(leader));previous=uid
    validate_groups(result)
    return result


def validate_groups(groups):
    if not 1<=len(groups)<=8:raise ValueError('Union roster size')
    for uid,value in groups.items():
        if type(uid) is not int or not 1001<=uid<2**63:raise ValueError('Union member UID')
        if (type(value) is not tuple or len(value)!=2 or type(value[0]) is not int
            or value[0] not in (0,1) or type(value[1]) is not bool):raise ValueError('Union member assignment')
    for group in (0,1):
        values=[leader for number,leader in groups.values() if number==group]
        if len(values)>4 or sum(values)!=(1 if values else 0):raise ValueError('Union group leadership')


def ordered_members(party):
    groups=party['union_groups'];validate_groups(groups)
    members=tuple(party['members'])
    if len(set(members))!=len(members) or {s.account.uid for s in members}!=set(groups):raise ValueError('Union roster mismatch')
    records=[]
    for group in (0,1):
        # Explicit waiting-room compatibility policy: stable party order after
        # the source-designated group leader, whose original slot is0 or4.
        selected=[s for s in members if groups[s.account.uid][0]==group]
        selected.sort(key=lambda s:not groups[s.account.uid][1])
        records.extend((s,4*group+i,group,groups[s.account.uid][1]) for i,s in enumerate(selected))
    return records


def ack(result=0):
    # Original2D17450 consumes exactly one signed int, without a string.
    return Event(0x201,kind=0xaa2,payload=struct.pack('>i',result))


def member_vector(party):
    records=ordered_members(party)
    return wire.u32(len(records))+b''.join(
        wire.party_member(party['id'],s,index,s is party['leader'],s in party['ready'],group=group,group_leader=leader)
        for s,index,group,leader in records)


def snapshot(party):
    return Event(0x201,kind=0xaa3,payload=member_vector(party))


def group_stage(group, dungeon, stage):
    # 2D7ADD0 passes the zero-based stage to the native StageInfo movie.
    return Event(0x201,kind=0xaa8,payload=struct.pack('>iii',group,dungeon,stage))


def group_finished(group, dungeon, cleared):
    return Event(0x201,kind=0xaa7,payload=struct.pack('>iiB',group,dungeon,cleared))


def battle_ack(result=0):
    # AA5 -> C27A9A -> 7B3160 reads one i32.
    return Event(0x201,kind=0xaa5,payload=struct.pack('>i',result))


def battle_signal(payload):
    # AA4 (11184E0) and AA6 (C27C38) share the native integer fields.
    return Event(0x201,kind=0xaa6,payload=payload)
