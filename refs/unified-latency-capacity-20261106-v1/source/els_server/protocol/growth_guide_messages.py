"""Current native CAA and CAC/CAE/D0E layouts, consumed by33A3FF0."""
import struct
from els_server.protocol.protocol_codec import Event

def state(graduated,*,kind=0xcaa,result=0):
    # 33A4B70+ECA: the final bool selects the graduation page. Entry623
    # availability is separate. Zero u64 means no pending course popup bits;
    # quest rewards remain separate F4/F5 actions.
    if type(graduated) is not bool or kind not in (0xcaa,0xcac,0xcae,0xd0e):raise ValueError('Growth guide state')
    payload=struct.pack('>QB',0,graduated)
    if kind!=0xcaa:payload=struct.pack('>i',result)+payload
    return Event(0x201,kind=kind,payload=payload)

def request(kind,payload):
    if kind==0xcab:
        if len(payload)!=5:raise ValueError('Growth guide course request')
        step,flag=struct.unpack('>iB',payload)
        if not 0<=step<13 or flag not in (0,1):raise ValueError('Growth guide course field')
        return step
    if kind in (0xcad,0xd0d) and payload==b'':return None
    raise ValueError('Growth guide request')
