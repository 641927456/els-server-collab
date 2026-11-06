"""Current5FF smith single-hammer flags and600 XP/anvil fields."""
import struct
from els_server.protocol.paid_enhancement_messages import acknowledgement as ordinary_ack

def is_candidate(payload):
    # Route only the actual profession flag, never the third i32(scene choice).
    return isinstance(payload,bytes) and len(payload)==25 and payload[16]==1

def _decoded(payload):
    if not isinstance(payload,bytes) or len(payload)!=25:raise ValueError('Smith enhancement request size')
    uid,mode,scene_choice,a,b,c,d,context,e=struct.unpack('>QiiBBBBiB',payload)
    if (not 1<=uid<2**63 or mode not in (0,1,2) or scene_choice!=0
        or (a,c,d)!=(1,1,0) or b not in (0,1) or e not in (0,1) or b and e):
        raise ValueError('Unqualified smith helper, scene or mode combination')
    return uid,mode,context,bool(b),bool(e)

def options(payload):
    # Preserve the established caller's three-value API.
    return _decoded(payload)[:3]

def hammer_selection(payload):
    row=_decoded(payload)
    return 'el' if row[3] else 'smith' if row[4] else None

def acknowledgement(ed=0,uid=0,level=0,outcome=0,changes=(),result=0,*,profession_xp=0,anvil=None):
    if type(profession_xp) is not int or not 0<=profession_xp<2**31:raise ValueError('Smith XP wire bound')
    wire=ordinary_ack(ed,uid,level,outcome,changes,result)
    # Original2B4ECE0: u8, i32XP, u64, fivei32, anvil21B, remaining13B.
    # Keep existing unused/anvil compatibility fields; ProfessionState is4C4.
    offset=len(wire)-67+1
    wire=wire[:offset]+struct.pack('>i',profession_xp)+wire[offset+4:]
    if anvil is not None:
        from els_server.protocol.anvil_messages import state_wire as anvil_wire
        if not isinstance(anvil,dict):raise ValueError('Smith anvil snapshot type')
        state=anvil_wire(anvil['hammers'],anvil['ready_at'])
        # Current600 tail:33B prefix,21B anvil,13B remainder. XP stays at+1.
        begin=len(wire)-34;wire=wire[:begin]+state+wire[begin+21:]
    return wire
