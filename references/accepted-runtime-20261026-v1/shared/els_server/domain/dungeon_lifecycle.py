"""DX11 death-report schema; reward-bearing fields remain opaque.

Request: 2B4CCF0 / DB65D0 / DAEE70. AF: 83E630, independent 38-byte
native parse accepted. Only the isolated NPC-slot experiment uses this so far.
"""
import math,struct
from els_server.protocol.protocol_codec import Event

def death_report(payload):
    pos=0
    def read(fmt):
        nonlocal pos
        fmt='>'+fmt;n=struct.calcsize(fmt)
        if pos+n>len(payload):raise ValueError('Truncated death report')
        values=struct.unpack_from(fmt,payload,pos);pos+=n
        return values[0] if len(values)==1 else values
    def mapping(fmt):
        count=read('I')
        if count>80:raise ValueError('Death map bound')
        result={}
        for _ in range(count):
            key,value=read('Q'+fmt)
            if key in result:raise ValueError('Duplicate death map key')
            if fmt=='B' and value not in (0,1):raise ValueError('Death map bool')
            if fmt=='f' and not math.isfinite(value):raise ValueError('Death map scalar')
            result[key]=value
        return result
    index,flag,source,killer,*xyz=read('iBQQ6f')
    status,hp_bits=read('BI')
    contribution=mapping('f');readiness=mapping('B');extra_uid=read('Q')
    counters=mapping('i');last_uid=read('Q')
    # Native 16E1760 expiry uses signed-byte -1. Session authorization keeps
    # this distinct from enemy kills; decoding it never grants a clear.
    if pos!=len(payload) or flag not in (0,1,255) or not all(math.isfinite(v) for v in xyz):raise ValueError('Malformed death report')
    return {'index':index,'flag':flag,'source':source,'killer':killer,'xyz':tuple(xyz),
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
