"""DX11 AD request (2B4CCF0 / DB65D0 / DAEE70) and AE/AF responses."""
import math,struct
from els_server.protocol.protocol_codec import Event

_HEADER=struct.Struct('>iBQQ6fBI')
_COUNT=struct.Struct('>I')
_UID=struct.Struct('>Q')
_CONTRIBUTION=struct.Struct('>Qf')
_READINESS=struct.Struct('>QB')
_COUNTERS=struct.Struct('>Qi')
_MINIMUM=_HEADER.size+3*_COUNT.size+2*_UID.size


def death_envelope(event):
    return (event.performers==(0,) and event.uid==event.target_uid==2**64-1
            and event.payload_mode==0)


def _read_map(payload,pos,end,layout):
    if pos+_COUNT.size>end:raise ValueError('Truncated death report')
    count,=_COUNT.unpack_from(payload,pos)
    if count>80:raise ValueError('Death map bound')
    pos+=_COUNT.size
    stop=pos+count*layout.size
    if stop>end:raise ValueError('Truncated death report')
    result={}
    for offset in range(pos,stop,layout.size):
        key,value=layout.unpack_from(payload,offset)
        if key in result:raise ValueError('Duplicate death map key')
        if layout is _READINESS and value not in (0,1):raise ValueError('Death map bool')
        if layout is _CONTRIBUTION and not math.isfinite(value):raise ValueError('Death map scalar')
        result[key]=value
    return result,stop


def death_report(payload):
    end=len(payload)-_UID.size
    if len(payload)<_MINIMUM:raise ValueError('Truncated death report')
    head=_HEADER.unpack_from(payload)
    index,flag,source,killer=head[:4]
    xyz=head[4:10]
    status,hp_bits=head[10:]
    # Native 16E1760 expiry uses signed-byte -1. Session authorization keeps
    # this distinct from enemy kills; decoding it never grants a clear.
    if flag not in (0,1,255) or not all(map(math.isfinite,xyz)):raise ValueError('Malformed death report')
    contribution,pos=_read_map(payload,_HEADER.size,end,_CONTRIBUTION)
    readiness,pos=_read_map(payload,pos,end,_READINESS)
    if pos+_UID.size>end:raise ValueError('Truncated death report')
    extra_uid,=_UID.unpack_from(payload,pos)
    counters,pos=_read_map(payload,pos+_UID.size,end,_COUNTERS)
    if pos!=end:raise ValueError('Malformed death report')
    last_uid,=_UID.unpack_from(payload,end)
    return {'index':index,'flag':flag,'source':source,'killer':killer,'xyz':xyz,
            'status':status,'hp_bits':hp_bits,'contribution':contribution,'readiness':readiness,
            'extra_uid':extra_uid,'counters':counters,'last_uid':last_uid}

def death_ack():return Event(0x201,kind=0xae,payload=bytes(4))

def empty_reward_death_notice(npc_id,killer):
    # Local prototype: native death-code defaults and empty reward containers.
    # No claim that these are the retail reward values or formulas.
    return Event(0x201,kind=0xaf,payload=struct.pack('>iiBQII?iiI',npc_id,0,0,killer,0,0,False,0,0,0))

def experience_death_notice(npc_id,killer,owner,experience):
    """Verified AF UID map: one primary increment; party/A/B/Artifact zero."""
    if type(owner) is not int or not 1001<=owner<=2**63-1 or type(experience) is not int or not 0<=experience<=2**31-1:
        raise ValueError('AF experience owner/amount bound')
    empty=empty_reward_death_notice(npc_id,killer)
    if not experience:return empty
    record=struct.pack('>QiiiiQQ',owner,experience,0,0,0,0,0)
    return Event(0x201,kind=0xaf,payload=empty.payload[:17]+struct.pack('>I',1)+record+empty.payload[21:])

def part_end_notice(part):return Event(0x201,kind=0xba,payload=struct.pack('>b',part))
