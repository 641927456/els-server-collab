"""Current native free-practice lobby and finite team-1v1 room wire.

NPC2157D30/2158110, lobby317C640 and room3195F60 own these events.
No practice AP, rating, experience or item reward is encoded here.
"""
import struct
from els_server.protocol.local_messages import i32, u32, wstring
from els_server.protocol.protocol_codec import Event
from els_server.protocol.social_messages import Reader
from els_server.protocol import pvp_room_messages

CHANNEL = 9  # Current Enum.PCC_FREE; PCC_PLAY11 has different MP behaviour.


def event(kind, body):
    return Event(0x201, kind=kind, payload=body)


def channels():
    # Ratings do not restrict the free-practice channel.
    return event(0x4d, i32(0)+u32(CHANNEL)+u32(1)+struct.pack('>iiIB',0,2**31-1,CHANNEL,CHANNEL))


def list_request(payload):
    r=Reader(payload)
    page,mode,room=r.scalar('I'),r.scalar('b'),r.scalar('q')
    r.end()
    if page<1 or mode not in(-1,0,1,2,6,8) or room not in(-1,0) and room<1:
        raise ValueError('Practice native room-list filter')
    return page,mode,room


def room_list(page, rows, *, pages=1):
    return event(0x56,i32(0)+u32(pages)+u32(page)+u32(len(rows))+b''.join(rows)+b'\0')


def _room(r):
    # Complete current D9BCC0 field sequence. Read the entire request before
    # selecting the finite supported settings; client endpoint/owner fields
    # never become identity or transport authority.
    values={}
    for name,fmt in (('type','b'),('uid','Q'),('number','I')):values[name]=r.scalar(fmt)
    values['title']=r.text()
    for name in ('state','public','balance'):values[name]=r.scalar('b')
    values['password']=r.text()
    values['maximum'],values['count']=r.scalar('b'),r.scalar('b')
    r.text();r.scalar('H');r.text()
    for name in ('game_type','match_type','sub_type'):values[name]=r.scalar('b')
    values['channel']=r.scalar('i')
    values['kills'],values['limit']=r.scalar('b'),r.scalar('b')
    values['seconds']=r.scalar('f')
    values['map'],values['show_map']=r.scalar('h'),r.scalar('h')
    for fmt in ('Q','i','b','i','b','b','Q','Q','i','b'):r.scalar(fmt)
    count=r.scalar('I')
    if count>64:raise ValueError('Practice native room map count')
    for _ in range(count):r.scalar('h');r.scalar('i')
    for fmt in ('b','b','i','?','b','Q'):r.scalar(fmt)
    count=r.scalar('I')
    if count>64:raise ValueError('Practice native room player count')
    for _ in range(count):r.scalar('i');r.scalar('i')
    for fmt in ('b','i','Q','Q'):r.scalar(fmt)
    return values


def create_request(payload):
    r=Reader(payload);observer=r.scalar('?');value=_room(r);flag=r.scalar('?');r.end()
    if (observer or flag or value['maximum']!=2 or value['game_type']!=0
            or value['match_type']!=0 or value['sub_type']!=0
            or value['channel']!=CHANNEL or value['kills']!=1
            or value['seconds']not in(200.0,300.0) or value['balance']!=0
            or value['map'] not in pvp_room_messages.TEAM_MAPS|{-1,-2}
            or not value['title'] or len(value['title'])>40 or len(value['password'])>16):
        raise ValueError('Practice supports current free-channel team1v1, one life, verified duration')
    return value


def join_request(payload):
    r=Reader(payload)
    uid,password=r.scalar('Q'),r.text()
    observer,invited,team,slot=r.scalar('?'),r.scalar('?'),r.scalar('b'),r.scalar('b')
    r.end()
    if uid<1 or observer or invited or team not in(-1,0,1) or slot not in(-1,0,1):
        raise ValueError('Practice ordinary native room join')
    return uid,password


def start_request(payload):
    r=Reader(payload);world,seed=r.scalar('h'),r.scalar('I');r.end()
    if world not in pvp_room_messages.TEAM_MAPS|{-1,-2}:
        raise ValueError('Practice original start map')
    return world,seed


def slot(s,index,*,state=3,ready=False,host=False,capture=None):
    header=bytes((index,state,int(host),int(ready),0,0))+i32(index)
    if s is None:return header+bytes(12)
    from els_server.protocol.dungeon_messages import member
    character=s.account.character()
    body=member(s.account.get_skills(),character,s.account.get_inventory_snapshot()['items'],
        account_id=s.account.account_id,peer_port=21100+index,capture=capture)
    return header+u32(1)+body+bytes(8)


def room_info(room,port,*,count=None,state=3,listing=False):
    members=len(room.members)if count is None else count
    return pvp_room_messages.room_info(room.identity,room.map_id,port,channel=CHANNEL,
        title=room.title,password=''if listing else room.password,
        public=not bool(room.password),state=state,count=members,seconds=room.seconds)


def entered(kind,info,slots):
    # Both 5F and63 use this exact room+ordinary/observer vectors+CN IP.
    return event(kind,i32(0)+info+u32(len(slots))+b''.join(slots)+u32(0)+wstring(''))


def joined(body,count):
    return event(0x64,body+i32(count)+bytes(8))


def prepared(body):
    return event(0x90,b'\3'+body)


def start_notice(map_id,slots,seed):
    # 31BF3C0: roomstate, two native ints, world, ordinary slots, empty NPCs.
    return event(0x8d,struct.pack('>bIIhI',4,seed,0,map_id,len(slots))+b''.join(slots)+u32(0))


def departed(uid,slots):
    return event(0x6c,b'\3'+struct.pack('>Q',uid)+u32(len(slots))+b''.join(slots)+u32(0))
