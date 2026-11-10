"""Pinned native achievement records and the three ordinary account requests."""
import struct
from els_server.protocol.local_messages import i32, wstring
from els_server.protocol.protocol_codec import Event

REQUESTS=frozenset((0x6be,0x6c1,0x6c9))


def request(kind,payload):
    if type(payload)is not bytes:raise ValueError('Achievement request bytes required')
    if kind==0x6be:
        if payload:raise ValueError('Achievement snapshot request must be empty')
        return {}
    if kind in(0x6c1,0x6c9):
        if len(payload)!=4:raise ValueError('Achievement identity request size')
        identity=struct.unpack('>i',payload)[0]
        if identity<=0:raise ValueError('Achievement identity must be positive')
        return dict(achievement=identity)
    # 8178A0/841D80 produces6C3 from CHEAT_COMPLETE, gated by native user
    # permission. It is never an ordinary completion or reward request.
    raise ValueError('Unsupported ordinary achievement request')


def message(kind,payload):return Event(0x201,kind=kind,payload=payload)


def ids(values):return struct.pack('>I',len(values))+b''.join(i32(value)for value in values)


def completed_record(row):
    # Original2BE0010/2C248F0: i32, UTF16 byte-count string, bool.
    return i32(row['id'])+wstring(row['completed_at'])+bytes((int(row['received']),))


def completed_vector(rows):
    return struct.pack('>I',len(rows))+b''.join(completed_record(row)for row in rows)


def progress_map(rows):
    # Original2C24190: map<int,{int,vector<{int,int,bool}>}>.
    return struct.pack('>I',len(rows))+b''.join(
        struct.pack('>iiI',row['id'],row['id'],len(row['conditions']))+
        b''.join(struct.pack('>iiB',condition['id'],condition['count'],int(condition['complete']))
                 for condition in row['conditions'])for row in rows)


def completed_map(rows):
    # Original2C24610: map<int,{int,wstring,bool}>.
    return struct.pack('>I',len(rows))+b''.join(i32(row['id'])+completed_record(row)for row in rows)


def initialization(extra_ids,progress,completed,watched):
    # Original816F40 copies the first vector to manager+80, then the two
    # maps to+48/+58 and the final display vector to+68.
    return message(0x6bf,ids(extra_ids)+progress_map(progress)+completed_map(completed)+ids(watched))


def watch_ack(result,watched):return message(0x6c2,i32(result)+ids(watched))


def status(points,watched,state_flag):
    if len(points)!=4 or any(type(v)is not int or not 0<=v<2**31 for v in points):
        raise ValueError('Four native achievement category totals required')
    if type(state_flag)is not bool:raise ValueError('Explicit native achievement state flag required')
    return ids(points)+ids(watched)+bytes((int(state_flag),))


def summary(points,watched,state_flag):
    return message(0x6c7,status(points,watched,state_flag))


def completion(rows,points,watched,state_flag):
    # Original816650 reads completed records, four category scores, displays
    # and the existing user flag, then invokes the original completion UI.
    if not rows:raise ValueError('Achievement completion notice requires new completions')
    return message(0x6c0,completed_vector(rows)+status(points,watched,state_flag))


def reward_ack(result,achievement,completed_at,received):
    # UASCM_COMPLETE_REWARD ->14444 ->817DF0 ->8424C0 sends6C9.
    # Original817F10 consumes6CA and updates the completed record's flag.
    return message(0x6ca,i32(result)+completed_record(dict(id=achievement,completed_at=completed_at,received=received)))
