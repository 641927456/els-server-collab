"""Native2351E10/2352170 writers;226BF50/226C9C0 and13890C0 readers."""
import struct
from els_server.protocol.protocol_codec import Event


def register_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=8:raise ValueError('Wardrobe register payload')
    uid=struct.unpack('>Q',payload)[0]
    if not 0<uid<2**63:raise ValueError('Wardrobe item UID')
    return uid


def apply_request(payload):
    # map<int,{int template,Q targetUID,array<int,3>}>. Tags are implicit.
    if not isinstance(payload,bytes) or len(payload)<4:raise ValueError('Wardrobe apply payload')
    count=struct.unpack_from('>I',payload)[0]
    if not 1<=count<=32 or len(payload)!=4+32*count:raise ValueError('Wardrobe apply count/size')
    rows=[];keys=set();uids=set()
    for n in range(count):
        position,template,uid,size,a,b,c=struct.unpack_from('>iiQIiii',payload,4+32*n)
        if position in keys or uid in uids or size!=3 or min(a,b,c)<0 or not 0<uid<2**63 or template<=0:
            raise ValueError('Wardrobe duplicate, dye or invalid fields')
        keys.add(position);uids.add(uid);rows.append((position,template,uid,(a,b,c)))
    return rows


def registry_wire(counts):
    if len(counts)>72885 or any(type(k)is not int or not 0<k<2**31 or type(v)is not int or not 1<=v<2**31 for k,v in counts.items()):
        raise ValueError('Wardrobe registry bounds')
    return struct.pack('>I',len(counts))+b''.join(struct.pack('>ii',k,v)for k,v in sorted(counts.items()))


def favorite_request(payload):
    if not isinstance(payload,bytes)or len(payload)!=8:raise ValueError('Wardrobe favorite payload')
    mode,template=struct.unpack('>ii',payload)
    if mode not in (1,2)or template<=0:raise ValueError('Wardrobe favorite fields')
    return mode,template


def favorite_wire(values):
    values=sorted(values)
    if len(values)>100 or len(set(values))!=len(values)or any(type(v)is not int or not 0<v<2**31 for v in values):
        raise ValueError('Wardrobe favorite set bounds')
    return struct.pack('>I',len(values))+b''.join(struct.pack('>i',v)for v in values)


def initialization(counts,favorites=()):
    # Native13890C0 installs manager+338 and manager+3E0 respectively.
    return Event(0x201,kind=0x31,payload=bytes(4)+registry_wire(counts)+favorite_wire(favorites))


def acknowledgement(kind,counts=None,changes=(),result=0,*,favorite_values=(),favorite_mode=0):
    from els_server.domain.fashion_state import move_ack
    if kind==0xbee:
        # Native B824D0: result, action, complete set<int> (replaces favorites).
        return Event(0x201,kind=0xbef,payload=struct.pack('>ii',result,favorite_mode)+favorite_wire(favorite_values))
    if kind==0xad6:
        return Event(0x201,kind=0xad7,payload=struct.pack('>i',result)+move_ack(changes)[:-4])
    if kind not in (0x4af,0x4b1,0x4f4,0x565,0x6d7):raise ValueError('Wardrobe operation kind')
    # Both readers consume result, map<int,int>, then DD46E0 inventory vector.
    return Event(0x201,kind=kind+1,payload=struct.pack('>i',result)+registry_wire(counts or {})+move_ack(changes)[:-4])

def ticket_request(kind,payload):
    if not isinstance(payload,bytes)or len(payload)!=12:raise ValueError('Wardrobe ticket size')
    template,uid=struct.unpack('>iQ',payload)if kind==0x4f4 else tuple(reversed(struct.unpack('>Qi',payload)))
    if not 0<uid<2**63 or template<=0:raise ValueError('Wardrobe ticket fields')
    return uid,template

def unregister_request(payload):
    if not isinstance(payload,bytes)or len(payload)!=16:raise ValueError('Hanger removal size')
    scroll,uid=struct.unpack('>QQ',payload)
    if not 0<scroll<2**63 or not 0<uid<2**63 or scroll==uid:raise ValueError('Hanger removal UIDs')
    return scroll,uid

def dye_request(payload):
    if not isinstance(payload,bytes)or len(payload)<19:raise ValueError('Dye request size')
    uid,palette,n=struct.unpack_from('>QiI',payload)
    if not 0<uid<2**63 or palette<=0 or not 1<=n<=3 or len(payload)!=19+8*n:raise ValueError('Dye request fields')
    rows=[struct.unpack_from('>ii',payload,16+8*i)for i in range(n)]
    flags=payload[-3:]
    if len(dict(rows))!=n or any(p not in (0,1,2)or c<0 for p,c in rows)or flags[0]>1 or flags[1]>1 or flags[2]!=0 or flags[:2]==b'\1\1':raise ValueError('Dye request parts/flags')
    return uid,palette,dict(rows),bool(flags[0]),bool(flags[1])

def ticket_information(payload):
    from els_server.domain.wardrobe_extensions import catalog
    from els_server.game_data import client_data
    if not isinstance(payload,bytes)or len(payload)!=5:raise ValueError('Ticket info size')
    page,force=struct.unpack('>iB',payload)
    data=catalog();keys=sorted(int(k)for k,v in data['ticket_allowed'].items()if v)
    if not 0<=page<len(keys)or force>1:raise ValueError('Ticket info page')
    key=str(keys[page]);ticket=data['tickets'][key];allowed=data['ticket_allowed'][key]
    ints=lambda xs:struct.pack('>I',len(xs))+b''.join(struct.pack('>i',x)for x in xs)
    # BC8A20/2C233E0: (template, group, position set, reserved set).
    head=struct.pack('>Iii',1,int(key),ticket['group_id'])+ints([ticket['part']])+ints([])
    # 2BE9FF0/2BDDB40: group -> map<unit_type, vector<template>>.
    roles={}
    for t in allowed:roles.setdefault(client_data().item(t)['record'][0xd2],[]).append(t)
    groups=struct.pack('>Iii',1,ticket['group_id'],len(roles))+b''.join(struct.pack('>i',r)+ints(ts)for r,ts in sorted(roles.items()))
    return Event(0x201,kind=0x564,payload=bytes(4)+head+groups+struct.pack('>iBB',page,int(page==len(keys)-1),force))

def color_notification(action,uid,template,colors,flag=0,previous=0):
    if action not in (0,1,2,3)or len(colors)!=3:raise ValueError('Dye notification')
    return Event(0x201,kind=0xad5,payload=struct.pack('>iQiIiiiBQ',action,uid,template,3,*colors,flag,previous))
