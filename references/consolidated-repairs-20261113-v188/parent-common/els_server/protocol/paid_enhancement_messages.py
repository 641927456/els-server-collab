"""Original 5FF enhancement request and 600 result container."""
import struct
from els_server.domain.fashion_state import record,empty_record


def options(payload):
    # 24339D0: UID,Q; mode/profession,i32; four bools; context,i32; bool.
    if not isinstance(payload,bytes) or len(payload)!=25:raise ValueError('Enhancement request size')
    uid,mode,profession,a,b,c,d,context,e=struct.unpack('>QiiBBBBiB',payload)
    if not 1<=uid<2**63 or mode not in (0,1,2,4) or b not in (0,1) or d not in (0,1) or mode==4 and b or (profession,a,c,e)!=(0,0,1,0):
        raise ValueError('Unsupported enhancement mode or helper item')
    # 23EB0B5 copies widget +EA into DTO +13 (wire byte 19).
    return uid,mode,context,bool(b),bool(d)


def details(payload):
    return options(payload)[:4]

def request(payload):
    uid,mode,context,hammer=details(payload)
    return uid,context

def hammer_initialization():
    # B7E57A switch: 77F -> BD8D80, vector<int> -> global core +F20.
    from els_server.domain.advanced_enhancement_materials import catalog
    from els_server.protocol.protocol_codec import Event
    items=catalog()['hammer_templates']
    return Event(0x201,kind=0x77f,payload=struct.pack('>I',len(items))+b''.join(struct.pack('>i',t) for t in items))


def acknowledgement(ed=0,uid=0,level=0,outcome=0,changes=(),result=0):
    # 2B4ECE0: original 600 DTO reader. This path has no profession metadata.
    # Auto recovery uses primary outcome 8 and the final
    # equipment/material rows; its unused auxiliary containers remain empty.
    body=struct.pack('>iQiQiI',result,ed,outcome,uid,level,len(changes))
    body+=b''.join(empty_record(*p) if item is None else record(item) for p,item in changes)
    return body+bytes(33+21+13)
