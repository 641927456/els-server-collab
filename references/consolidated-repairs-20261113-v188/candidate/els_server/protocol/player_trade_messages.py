"""Current 174..18B trade contracts; amounts are u64, never legacy i32."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.domain.inventory_items import item_body
from els_server.protocol.trade_board_messages import _changes_wire

REQUESTS=frozenset((0x174,0x177,0x17a,0x17f,0x182,0x185,0x188))

def request(kind,payload):
    if type(payload)is not bytes:raise ValueError('Native trade body')
    if kind==0x174 and len(payload)==8:
        return dict(target=struct.unpack('>Q',payload)[0])
    if kind==0x177 and len(payload)==13:
        target,accept,reason=struct.unpack('>QBi',payload)
        if accept>1:raise ValueError('Trade invitation response boolean')
        return dict(target=target,accept=bool(accept),reason=reason)
    if kind==0x17a and len(payload)==4:
        return dict(reason=struct.unpack('>i',payload)[0])
    if kind==0x17f and len(payload)==13:
        uid,count,delete=struct.unpack('>QiB',payload)
        if delete>1 or not 0<uid<2**63 or not delete and count<=0:
            raise ValueError('Native offered item scalars')
        return dict(uid=uid,count=count,delete=bool(delete))
    if kind==0x182 and len(payload)==8:
        return dict(ed=struct.unpack('>Q',payload)[0])
    if kind in(0x185,0x188)and not payload:return {}
    raise ValueError('Native trade request length or kind')

def event(kind,body):return Event(0x201,kind=kind,payload=body)

def acknowledgement(kind,*,result=0,target=0,name='',text=''):
    body=struct.pack('>i',(123) if result == -1 else result)
    if kind==0x174:body+=struct.pack('>Q',target)+wstring(name)+wstring(text)
    elif kind in(0x17f,0x182):body+=wstring(text)
    elif kind not in(0x17a,0x185,0x188):raise ValueError('Native trade ACK kind')
    return event(kind+1,body)

def invitation(uid,name):return event(0x176,struct.pack('>Q',uid)+wstring(name))
def denied(uid,result):return event(0x178,struct.pack('>iQ',result,uid))
def created(trade):return event(0x179,struct.pack('>Q',trade))
def cancelled(reason):return event(0x17c,struct.pack('>i',reason))

def user(row):
    #2C1B140 record: server/account/character identities, name, ED, last byte.
    # The final field is copied but unused by both current17D/17E consumers.
    return (struct.pack('>QQQ',1,row['account_id'],row['uid'])+wstring(row['name'])
            +struct.pack('>QB',row['ed'],0))

def members(rows):return event(0x17d,struct.pack('>I',len(rows))+b''.join(user(r)for r in rows))
def joined(row):return event(0x17e,user(row))

def offers(states):
    return struct.pack('>I',len(states))+b''.join(struct.pack('>Q?',uid,ready)for uid,ready in sorted(states.items()))

def item_changed(owner,item,delete,states):
    return event(0x181,struct.pack('>QQ?',owner,item['uid'],delete)+item_body(item)+offers(states))

def ed_changed(owner,ed,states):return event(0x184,struct.pack('>QQ',owner,ed)+offers(states))
def registered(owner):return event(0x187,struct.pack('>Q',owner))
def approved(owner):return event(0x18a,struct.pack('>Q',owner))
def completed(ed,changes):return event(0x18b,_changes_wire(changes)[0]+struct.pack('>Q',ed))
