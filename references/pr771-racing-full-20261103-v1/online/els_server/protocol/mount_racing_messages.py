"""Current native racing selection, saved booster map and result DTO."""
import math,struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.mount_messages import record,growth_record
from els_server.domain.inventory_items import inventory_payload


def selection(result=0,uid=0,mounts=()):
    return Event(0x201,kind=0xa8a,payload=struct.pack('>iQI',result,uid,len(mounts))+b''.join(record(m)for m in mounts))


def mode(result=0,uid=0,enabled=False):
    return Event(0x201,kind=0xa8c,payload=struct.pack('>iQB',result,uid,int(enabled)))


def member_mount(owner,mount,enabled=True):
    # Party dispatcher2D58770/A8D ->2E09E60 installs Qowner,DB2B20,bool.
    return Event(0x201,kind=0xa8d,payload=struct.pack('>Q',owner)+growth_record(mount)+bytes((int(enabled),)))


def booster_map(plans):
    parts=[]
    for uid,p in sorted(plans.items(),key=lambda v:int(v[0])):
        body=struct.pack('>Qiif',int(uid),p['lane'],*p['start'])
        for key in('normal','obstacle'):
            body+=struct.pack('>I',len(p[key]))+b''.join(struct.pack('>if',*v)for v in p[key])
        body+=struct.pack('>iffI',*p['spurt'],p['remain'],0)
        parts.append(body)
    return Event(0x201,kind=0xa85,payload=struct.pack('>I',len(parts))+b''.join(parts))


def finish_request(payload,members):
    # Original2C188C0 writes the map FIRST and one float at the end.
    # This is a display report/ACK trigger; it cannot choose server standings.
    if type(payload)is not bytes or len(payload)<8:raise ValueError('Racing finish report')
    count=struct.unpack_from('>I',payload)[0]
    if count!=len(members)or len(payload)!=8+20*count:raise ValueError('Racing finish roster length')
    rows=[struct.unpack_from('>Qiff',payload,4+20*i)for i in range(count)]
    duration=struct.unpack_from('>f',payload,4+20*count)[0]
    if ({r[0]for r in rows}!=set(members)or len({r[0]for r in rows})!=count
            or {r[1]for r in rows}!=set(range(1,count+1))
            or not math.isfinite(duration)or not 0<=duration<=180
            or any(not math.isfinite(t)or not 0<t<=180 or not math.isfinite(speed)or not 0<speed<=10 for uid,rank,t,speed in rows)):
        raise ValueError('Racing finish display fields')
    return rows,duration


def finish_ack(result=0):return Event(0x201,kind=0xa87,payload=struct.pack('>i',result))


def result(data,mount,receipt,changes=(),*,roster=None):
    ranked=data['standings']
    body=struct.pack('>I',len(ranked))+b''.join(struct.pack('>Qif',r['uid'],r['rank'],r['time'])for r in ranked)
    # DB3650 optional native item map, local earned XP, optional float,
    # full current growth DTO and current changed inventory records.
    from els_server.domain.fashion_state import record as item_record,empty_record
    inventory=struct.pack('>I',len(changes))+b''.join(empty_record(*p)if item is None else item_record(item)for p,item in changes)
    body+=struct.pack('>Iif',0,receipt['experience_gained'],0.)+growth_record(mount)+inventory
    item_rows=[];experience_rows=[]
    for uid,award in sorted(data['awards'].items(),key=lambda v:int(v[0])):
        reward=award['reward'];item=reward['item'];kind=reward['bonus_type']
        if item:item_rows.append(struct.pack('>Qii',int(uid),item['template'],item['quantity']))
        elif 0<=kind<6:
            from els_server.domain.mount_racing_rules import policy
            experience_rows.append(struct.pack('>Qif',int(uid),reward['experience'],policy()['experience_multiplier_percent'][kind]/100-1))
    body+=struct.pack('>I',len(item_rows))+b''.join(item_rows)+struct.pack('>I',len(experience_rows))+b''.join(experience_rows)
    # These two scalar fields have no witnessed consumer in this build;
    # preserve their constructor zero values. The final2C2AFA0 map is
    # character UID -> DB2B20, used by2B2F8C0's podium mount lookup.
    roster=roster or {}
    body+=struct.pack('>BiI',0,0,len(roster))
    body+=b''.join(struct.pack('>Q',uid)+growth_record(m)for uid,m in sorted(roster.items()))
    return Event(0x201,kind=0xa88,payload=body)


def admission(members,leader,identity,mounts,bootstrap_port):
    from els_server.protocol.dungeon_messages import member,room_metadata
    from els_server.protocol.local_messages import wstring
    if not 3<=len(members)<=6 or leader not in members:raise ValueError('Racing admission roster')
    slots=[]
    for lane,s in enumerate(members):
        body=member(s.account.get_skills(),s.account.character(),s.account.get_inventory_snapshot()['items'],
                    account_id=s.account.account_id,peer_port=21100+lane,mount=mounts[s])
        slots.append(bytes((lane,4,int(s is leader)))+bytes(3)+struct.pack('>iI',0,1)+body+bytes(8))
    # Original2D63FA0 selects CX2RidingPetRacingRoom for dungeon150060.
    room=room_metadata(150060,0,room_id=identity,name='GoGo Elrider',bootstrap_port=bootstrap_port)
    body=bytes(2)+room+struct.pack('>I',len(slots))+b''.join(slots)+bytes(4)+wstring('')+bytes(4)+struct.pack('>I10fI',1,*([1.]*10),0)
    return Event(0x201,kind=0x14a,payload=body),tuple(slots)


def play_start(slots):
    return Event(0x201,kind=0x96,payload=b'\5'+struct.pack('>I',len(slots))
                 +b''.join(slot[:1]+b'\5'+slot[2:]for slot in slots)+struct.pack('>i',150060))
