"""Same-build 31C3520/2BE2520 save and 13E11A0/2C28470 restoration."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.social_messages import Reader

FIELDS=('equipment','skills','resonance','guild','custom','synergy')


def record(value):
    name=value['name']
    # Native UI budget: twelve ASCII letters or six Chinese characters.
    if type(name)is not str or any(ord(c)<32 or ord(c)==127 for c in name):
        raise ValueError('Preset page name')
    if sum(1 if ord(c)<128 else 2 for c in name)>12:
        raise ValueError('Preset page name length')
    raw=name.encode('utf-16le')
    page=value['page'];indices=tuple(value[k]for k in FIELDS)
    if type(page)is not int or not 1<=page<=4 or any(type(v)is not int or not 0<=v<=255 for v in indices):
        raise ValueError('Preset page index')
    return struct.pack('>iI',page,len(raw))+raw+struct.pack('>6i',*indices)


def request(payload):
    r=Reader(payload)
    value=dict(page=r.scalar('i'),name=r.text(12))
    value.update((key,r.scalar('i'))for key in FIELDS);r.end()
    if record(value)!=payload:raise ValueError('Preset record boundary')
    return value


def acknowledgement(result=0):
    return Event(0x201,kind=0x95a,payload=struct.pack('>i',result))


def expanded(ed,*,result=0):
    # 313C1D0: result and u64 wallet; 958 supplies the new complete page map.
    return Event(0x201,kind=0x95c,payload=struct.pack('>iQ',result,ed))


def restoration(pages):
    # Map<int,record>. Each value repeats its page index; no result prefix.
    return Event(0x201,kind=0x958,payload=struct.pack('>I',len(pages))+
        b''.join(struct.pack('>i',p['page'])+record(p)for p in pages))


def equipment_selection(current,*,result=0):
    # 23C5500: result, 2BE03D0 state, DD46E0 changes, bool, u64.
    return Event(0x201,kind=0x785,payload=struct.pack('>i',result)+
        current.payload[4:]+struct.pack('>IBQ',0,1,0))
