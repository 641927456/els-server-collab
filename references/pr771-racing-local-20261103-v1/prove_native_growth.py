"""Original DE1310/DB2B20 decoder and D81DD0 updater, in private Unicorn."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path('G:/els');W=Path(__file__).resolve().parent
R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
from role_native_replay import Replay,IMAGE_SHA
sys.path.insert(0,str(R))
from els_server.protocol.mount_messages import record
from els_server.domain.mount_racing_rules import profile

def decode(r,raw,dto):
    data=r.alloc(len(raw));r.write(data,raw);buffer=r.alloc(48)
    r.write(buffer+8,struct.pack('<QQQ',data,data+len(raw),data+len(raw)))
    stream=r.alloc(40);r.call(0x3b6d140,stream);r.call(0x3b6d1c0,stream,buffer,0)
    r.call(0x7e1de0,dto+0x40)
    assert r.call(0xde1310,stream,dto)&255==1
    assert struct.unpack('<I',r.read(buffer+32,4))[0]==len(raw)

def read(r,dto):
    uid,unknown,level,exp=struct.unpack('<QHBi',r.read(dto+0x40,15))
    head,count=struct.unpack('<QQ',r.read(dto+0x4f,16));found={}
    def visit(node):
        if node==head:return
        assert len(found)<4
        key,value=struct.unpack('<ii',r.read(node+0x1c,8));assert key not in found
        found[key]=value
        visit(int.from_bytes(r.read(node,8),'little'))
        visit(int.from_bytes(r.read(node+0x10,8),'little'))
    visit(int.from_bytes(r.read(head+8,8),'little'))
    assert len(found)==count
    return dict(uid=uid,unknown=unknown,level=level,experience=exp,stats=found)

r=Replay();r.write(r.base+0x4817e70,bytes(8))
manager=r.alloc(0x188);mounts=r.alloc(0x100)
r.write(manager+0x58,struct.pack('<QQQ',mounts,mounts+0x100,mounts+0x100))
for i,uid in enumerate((1001011,1001012)):
    decode(r,record(dict(uid=uid,unit=105,stamina=120.)),mounts+i*0x80)
saved=profile(11300,{0:10,1:10,2:1,3:9})
incoming=r.alloc(0x80);raw=record(dict(uid=1001011,unit=105,stamina=120.,racing=saved))
decode(r,raw,incoming);decoded=read(r,incoming)
assert decoded==dict(uid=1001011,unknown=0,**saved)
r.call(0xd81dd0,manager,incoming+0x40,incoming+0x40)
applied=read(r,mounts);foreign=read(r,mounts+0x80)
assert applied==decoded
assert foreign==dict(uid=1001012,unknown=0,level=1,experience=0,stats={})
out=dict(ok=True,image_sha256=IMAGE_SHA,reader='DE1310/DB2B20',consumer='D81DD0',
    decoded=decoded,applied=applied,foreign_mount=foreign,wire_size=len(raw),
    sources={rel:hashlib.sha256((R/rel).read_bytes()).hexdigest()for rel in
      ('els_server/protocol/mount_messages.py','els_server/domain/mount_racing_rules.py','els_server/data/mount_racing_local.json')},
    private_Unicorn=True,live_process=False,original_EXE_KOM_modified=False,
    real_race_settlement=False,synthetic_growth_profile=True)
(W/'native-growth-profile.json').write_bytes((json.dumps(out,indent=2)+'\n').encode());print(json.dumps(out))
