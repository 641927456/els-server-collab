"""Pinned original decoders, private memory; no live client or game input."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs'),str(R)]
from role_native_replay import Replay,IMAGE_SHA
sys.path.insert(0,str(R))
from els_server.protocol import mount_racing_messages as wire
from els_server.protocol.mount_messages import record


def stream(r,raw):
    data=r.alloc(len(raw));r.write(data,raw);buffer=r.alloc(48)
    r.write(buffer+8,struct.pack('<QQQ',data,data+len(raw),data+len(raw)))
    s=r.alloc(40);r.call(0x3b6d140,s);r.call(0x3b6d1c0,s,buffer,0)
    return s,buffer


def tree(r,size):
    head=r.alloc(size);r.write(head,struct.pack('<QQQH',head,head,head,0x101));return head


def nodes(r,container,key_offset=0x20):
    head,count=struct.unpack('<QQ',r.read(container,16));found=[]
    def walk(node):
        if node==head:return
        assert len(found)<count
        walk(int.from_bytes(r.read(node,8),'little'));found.append(node)
        walk(int.from_bytes(r.read(node+16,8),'little'))
    walk(int.from_bytes(r.read(head+8,8),'little'));assert len(found)==count
    return found


r=Replay();source=json.loads((W/'native-inputs.json').read_bytes());plans=source['plans'];raw=wire.booster_map(plans).payload
s,buf=stream(r,raw);head=tree(r,0x80);container=r.alloc(16);r.write(container,struct.pack('<QQ',head,0))
iterator=r.alloc(16);r.write(iterator,struct.pack('<QQ',container,head))
assert r.call(0x2c2aab0,s,iterator)&255==1
assert int.from_bytes(r.read(buf+32,4),'little')==len(raw)
boosters=[]
for node in nodes(r,container):
    uid,lane,kind,speed=struct.unpack('<Qiif',r.read(node+0x20,20));p=plans[str(uid)]
    assert lane==p['lane']and kind==p['start'][0]and speed==p['start'][1]
    for offset,key in((0x34,'normal'),(0x4c,'obstacle')):
        begin,end=struct.unpack('<QQ',r.read(node+offset,16))
        pairs=[list(struct.unpack('<if',r.read(a,8)))for a in range(begin,end,8)]
        assert pairs==p[key]
    kind,speed,remain=struct.unpack('<iff',r.read(node+0x64,12))
    assert [kind,speed]==p['spurt']and remain==p['remain']
    boosters.append(dict(uid=uid,lane=lane,normal=len(p['normal']),obstacles=len(p['obstacle'])))

# Execute the actual A85 receiver, including its protected map-to-runtime loop.
# The race's visual Game exists; no scene/actor/renderer is fabricated.
state=r.alloc(0x500);game=r.alloc(0x1800);r.write(state+0x408,struct.pack('<Q',game))
s,notify=stream(r,raw);r.write(r.stack+0x20,struct.pack('<Q',notify))
r.call(0x32afd20,state,0,0,0)
start,last=struct.unpack('<QQ',r.read(game+0x1738,16));assert last-start==6*0xb0,last-start
runtime=[]
for address in range(start,last,0xb0):
    character=int.from_bytes(r.read(address,8),'little');lane=int.from_bytes(r.read(address+0x64,4),'little')
    assert lane==plans[str(character)]['lane']
    runtime.append(dict(uid=character,lane=lane))

data=source['data'];mount=source['mount'];owner=next(row['uid']for row in data['standings']if row['lane']==0)
award=data['awards'][str(owner)];p=award['profile'];mount['racing']=dict(p,stats={int(k):v for k,v in p['stats'].items()})
receipt=dict(experience_gained=award['experience_gained'],bonus_type=award['reward']['bonus_type'])
roster={int(k):dict(v,racing=dict(data['awards'][k]['profile'],stats={int(i):x for i,x in data['awards'][k]['profile']['stats'].items()}))for k,v in source['mounts'].items()}
raw_result=wire.result(data,mount,receipt,roster=roster).payload;s,buf=stream(r,raw_result);dto=r.alloc(0x9c)
for offset,size in((0x18,0x418),(0x67,0x30),(0x77,0x30),(0x8c,0x48)):
    r.write(dto+offset,struct.pack('<QQ',tree(r,size),0))
r.call(0x7e1de0,dto+0x30)
assert r.call(0x2b4fb20,s,dto)&255==1
assert int.from_bytes(r.read(buf+32,4),'little')==len(raw_result)
begin,end=struct.unpack('<QQ',r.read(dto,16));ranked=[struct.unpack('<Qif',r.read(a,16))for a in range(begin,end,16)]
assert ranked==[(row['uid'],row['rank'],row['time'])for row in data['standings']]
uid,unit,level,experience=struct.unpack('<QHBi',r.read(dto+0x30,15))
assert(uid,unit,level,experience)==(mount['uid'],mount['unit'],p['level'],p['experience'])
item_bonuses={struct.unpack('<Qii',r.read(n+0x20,16))[0]:struct.unpack('<ii',r.read(n+0x28,8))for n in nodes(r,dto+0x67)}
xp_bonuses={struct.unpack('<Qif',r.read(n+0x20,16))[0]:struct.unpack('<if',r.read(n+0x28,8))for n in nodes(r,dto+0x77)}
assert set(item_bonuses)|set(xp_bonuses)=={row['uid']for row in data['standings']if row['rank']<=3}
native_roster=[]
for node in nodes(r,dto+0x8c):
    character,mount_uid,mount_unit,mount_level,mount_exp=struct.unpack('<QQHBi',r.read(node+0x20,23))
    expected=roster[character]
    assert(mount_uid,mount_unit,mount_level,mount_exp)==(expected['uid'],expected['unit'],expected['racing']['level'],expected['racing']['experience'])
    native_roster.append(dict(character=character,mount=mount_uid,unit=mount_unit,level=mount_level,experience=mount_exp))
assert len(native_roster)==6

# The actual six-account admission generated by FriendsRacing, not a DTO-only
# mock. Constructor2D64DD0 owns the two slot vectors and native room metadata.
raw_room=bytes.fromhex(source['admission']);s,buf=stream(r,raw_room);room=r.alloc(0x1ac);r.call(0x2d64dd0,room)
try:room_ok=r.call(0x2b4d0d0,s,room)&255
except ValueError:
    from unicorn.x86_const import UC_X86_REG_RIP,UC_X86_REG_RAX
    pc=r.uc.reg_read(UC_X86_REG_RIP);consumed=int.from_bytes(r.read(buf+32,4),'little')
    # The base harness's1M-instruction budget stops after three of six real
    # FullUsers, at the pinned vector<int> copy47F790. Continue that same
    # finite call once, preserving every register/stack/heap; do not restart it.
    assert pc-r.base==0x47f7b6 and 0<consumed<len(raw_room),(hex(pc-r.base),consumed)
    r.uc.emu_start(pc,r.stop,count=2000000)
    assert r.uc.reg_read(UC_X86_REG_RIP)==r.stop
    room_ok=r.uc.reg_read(UC_X86_REG_RAX)&255
assert room_ok==1
assert int.from_bytes(r.read(buf+32,4),'little')==len(raw_room)
assert struct.unpack('<i',r.read(room+2+0xb2,4))[0]==150060
begin,end=struct.unpack('<QQ',r.read(room+0x114,16));assert end-begin==6*0x3e,end-begin
native_members=[]
for slot in range(begin,end,0x3e):
    user,last=struct.unpack('<QQ',r.read(slot+0xa,16));assert last>user
    character=int.from_bytes(r.read(user+0xe1,8),'little')
    mount_uid,mount_unit,mount_level,mount_exp=struct.unpack('<QHBi',r.read(user+0x604,15))
    assert str(character)in plans and mount_uid>0 and mount_unit==105 and mount_level==1 and mount_exp==0
    native_members.append(dict(character=character,mount=mount_uid,unit=mount_unit,level=mount_level,experience=mount_exp))
out=dict(ok=True,image_sha256=IMAGE_SHA,private_Unicorn=True,natural_GUI=False,live_process=False,
         private_fixture_sha256=hashlib.sha256((W/'native-inputs.json').read_bytes()).hexdigest(),
         original_EXE_KOM_modified=False,boosters=boosters,booster_wire_bytes=len(raw),
         result_wire_bytes=len(raw_result),native_standings=ranked,growth=dict(uid=uid,unit=unit,level=level,experience=experience),
         full_A85_receiver_returned=True,native_runtime=runtime,
         item_bonus_entries=len(item_bonuses),experience_bonus_entries=len(xp_bonuses),
         result_roster=native_roster,test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         admission_wire_bytes=len(raw_room),slot_vector_bytes=end-begin,native_members=native_members,
         sources={p:hashlib.sha256((R/p).read_bytes()).hexdigest()for p in('els_server/protocol/mount_racing_messages.py','els_server/protocol/mount_messages.py','els_server/protocol/dungeon_messages.py')})
(W/'native-racing-decoders.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8');print(json.dumps(out))
