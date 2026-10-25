"""DX11 C23 title book, 213/214 equipment and 217 mission progress."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32,u32,wstring

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=4:raise ValueError('Title request size')
    value=struct.unpack('>i',payload)[0]
    if value<0:raise ValueError('Title request bound')
    return value

def owned_record(row):
    # DD86B0: ID, expiry date string, epoch seconds, bool permanent, bool.
    # 2181550 inverts permanent into row+56; 217F310 expires at deadline<=now.
    from els_server.domain.item_expiration import date_string
    end=row.get('expires_at',0)
    return i32(row['title'])+wstring(date_string(end) if end else '')+struct.pack('>qBB',end,not bool(end),0)

def mission_record(row):
    # DD8270: int mission, byte flag, vector<int sub, int count, bool>.
    progress=row.get('progress',())
    return i32(row['mission'])+bytes([row.get('flag',0)])+u32(len(progress))+b''.join(struct.pack('>iiB',p['sub'],p['count'],p.get('done',False)) for p in progress)

def initialization(state,result=0):
    missions=state.get('missions',());owned=state.get('owned',())
    return Event(0x201,kind=0xc23,payload=i32(result)+u32(len(missions))+b''.join(mission_record(r) for r in missions)+u32(len(owned))+b''.join(owned_record(r) for r in owned))

def equipment(title=0,result=0):return Event(0x201,kind=0x214,payload=struct.pack('>ii',result,title))

def progress(rows):return Event(0x201,kind=0x217,payload=u32(len(rows))+b''.join(mission_record(r) for r in rows))
