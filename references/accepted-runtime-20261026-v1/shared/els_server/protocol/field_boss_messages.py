"""Drabaki battlefield codecs from C5FBF0/C4E010 and BFAD80.

Only field 40046 is admitted. Dungeon 34080 remains forbidden.
"""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32,u32,wstring
from els_server.protocol.social_messages import Reader

FIELD=40046


def join_request(payload):
    # C5FBF0 -> 2BDE4B0: i32,i32,vector<Q>,bool,bool,u16,bool,bool;
    # one further bool follows the shared header.
    r=Reader(payload);identity=r.scalar('i');position=r.scalar('i');count=r.scalar('I')
    if count>6:raise ValueError('Field participant vector')
    members=tuple(r.scalar('Q') for _ in range(count))
    flags=(r.scalar('B'),r.scalar('B'));channel=r.scalar('H')
    tail=(r.scalar('B'),r.scalar('B'),r.scalar('B'));r.end()
    if identity!=FIELD or not 0<=position<=65535 or any(f not in (0,1) for f in (*flags,*tail)):
        raise ValueError('Unsupported battlefield request')
    if len(set(members))!=len(members):raise ValueError('Field duplicate participant')
    return dict(identity=identity,position=position,members=members,channel=channel)


def room_info(room_id):
    # D9BCC0 shares the existing CBDCC0 room fields, including B2 map.
    data=b'\1'+struct.pack('>Q',room_id)+u32(0)+wstring('Drabaki')
    data+=b'\0\1\0'+wstring('')+b'\0\0'+wstring('')+bytes(2)+wstring('')
    data+=b'\0\xff\0'+i32(-1)+b'\0\0'+i32(0)+bytes(4)+bytes(8)+i32(0)
    data+=b'\0'+i32(FIELD)+b'\0\0'+bytes(8)*2+i32(0)+b'\0'
    data+=u32(0)+bytes(2)+i32(0)+b'\0\0'+bytes(8)+u32(0)
    return data+b'\0'+i32(0)+bytes(8)*2


def joined(members,leader,room_id,*,result=0,deadline=0):
    from els_server.protocol.dungeon_messages import member
    if not (result and not members) and (not 1<=len(members)<=6 or leader not in members):raise ValueError('Field room participants')
    teams=[]
    for index,s in enumerate(members):
        body=member(s.account.get_skills(),s.account.character(),s.account.get_inventory_snapshot()['items'],
                    account_id=s.identity['id'],peer_port=21100+index)
        teams.append(bytes([index,4 if s is leader else 0,int(s is leader)])+bytes(3)+i32(0)+u32(1)+body+u32(0)+bytes(4))
    header=i32(FIELD)+i32(0)+u32(0)+bytes(6)
    payload=i32(result)+header+room_info(room_id)+u32(len(teams))+b''.join(teams)
    # C4E010 DTO+154,174,178,17C,19C,19E,1BE,1D6,1DE,1DF.
    payload+=wstring('')+i32(0)*2+wstring('')+bytes(2)+wstring('')+u32(0)+struct.pack('>Q',deadline)+b'\0'+wstring('')
    return Event(0x201,kind=0x375,payload=payload)


def metrics_request(payload):
    # 7C14C0 -> 2BE0140 writes a map<Q,IIHBii>. These client metrics
    # are acknowledgable telemetry, never proof of a kill or grant amounts.
    r=Reader(payload);count=r.scalar('I')
    if count>6:raise ValueError('Field result metric count')
    uids=[]
    for _ in range(count):
        uids.append(r.scalar('Q'))
        for fmt in ('I','I','H','B','i','i'):r.scalar(fmt)
    r.end()
    if len(set(uids))!=len(uids):raise ValueError('Field duplicate result metric')
    return set(uids)


def ack(kind,result=0):
    if kind not in (0x37b,0x77b):raise ValueError('Field acknowledgement')
    return Event(0x201,kind=kind,payload=i32(result))


def started(deadline,result=0):return Event(0x201,kind=0x531,payload=struct.pack('>iQ',result,deadline))
def clock(deadline):return Event(0x201,kind=0x53b,payload=struct.pack('>Q',deadline))
def schedule(deadline):return Event(0x201,kind=0x536,payload=struct.pack('>iQQ',0,deadline,deadline))
def ended():return Event(0x201,kind=0x466,payload=b'')
