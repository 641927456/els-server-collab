"""Consume the candidate's real mount wire, then the original growth updater.

The synthetic level/EXP below distinguish an applied update from a no-op. They
are decoder fixtures, not a race award or a server growth writer.
"""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path('G:/els');W=Path(__file__).resolve().parent
R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
sys.path[:0]=[str(R),str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
from role_native_replay import Replay,IMAGE_SHA
sys.path.insert(0,str(R))
from els_server.protocol.mount_messages import record

def decode(r,raw,dto):
    data=r.alloc(len(raw));r.write(data,raw);buffer=r.alloc(48)
    r.write(buffer+8,struct.pack('<QQQ',data,data+len(raw),data+len(raw)))
    stream=r.alloc(40);r.call(0x3b6d140,stream);r.call(0x3b6d1c0,stream,buffer,0)
    r.call(0x7e1de0,dto+0x40)
    assert r.call(0xde1310,stream,dto)&255==1
    assert struct.unpack('<I',r.read(buffer+32,4))[0]==len(raw)

r=Replay();r.write(r.base+0x4817e70,bytes(8))
manager=r.alloc(0x188);mounts=r.alloc(0x100)
r.write(manager+0x58,struct.pack('<QQQ',mounts,mounts+0x100,mounts+0x100))
uids=(1001011,1001012)
for i,uid in enumerate(uids):
    decode(r,record(dict(uid=uid,unit=105,stamina=120.)),mounts+i*0x80)
target=r.alloc(0x30);r.call(0x7e1de0,target)
inner_uid=struct.unpack('<Q',r.read(mounts+0x40,8))[0]
r.write(target,struct.pack('<QHBi',inner_uid,0,2,200))
r.call(0xd81dd0,manager,target,target)
observed=[struct.unpack('<Bi',r.read(mounts+i*0x80+0x4a,5))for i in range(2)]
fixed=inner_uid==uids[0]
assert observed==([(2,200),(1,0)]if fixed else[(1,0),(1,0)])
result=dict(image_sha256=IMAGE_SHA,source_sha256=hashlib.sha256((R/'els_server/protocol/mount_messages.py').read_bytes()).hexdigest(),
    reader='DE1310/DB2B20',consumer='D81DD0',outer_uid=uids[0],nested_uid=inner_uid,
    observed=observed,update_applied=fixed,foreign_mount_unchanged=observed[1]==(1,0),
    private_Unicorn=True,synthetic_growth_fixture=True,server_experience_awarded=False,live_process=False)
name='native-mount-identity-'+('fixed'if fixed else'before')+'.json'
(W/name).write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))
