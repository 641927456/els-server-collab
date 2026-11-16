"""Execute the complete A8F receiver with UI closed; observe inventory apply."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs'),str(ROOT/'analysis/pr771-racing-local-20261103-v1')]
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8
sys.path.insert(0,str(R))
# Reuse the prior decoder/tree helpers only; its proof is not re-executed.
source=(ROOT/'analysis/pr771-racing-local-20261103-v1/prove_native_growth.py').read_text('utf8')
scope={'__file__':str(ROOT/'analysis/pr771-racing-local-20261103-v1/prove_native_growth.py')}
exec(compile(source.split('r=Replay();',1)[0],'<growth-helpers>','exec'),scope)
decode,read=scope['decode'],scope['read']
from els_server.protocol.mount_messages import record,reset_ack
from els_server.domain.mount_racing_rules import profile

r=Replay();manager=r.alloc(0x188);mounts=r.alloc(0x100)
r.write(manager+0x58,struct.pack('<QQQ',mounts,mounts+0x100,mounts+0x100))
initial=profile(11300,{0:10,1:10,2:1,3:9})
for i,uid in enumerate((1001011,1001012)):
    decode(r,record(dict(uid=uid,unit=105,stamina=120.,racing=initial)),mounts+i*0x80)
r.write(r.base+0x4817ec0,struct.pack('<Q',manager))
runtime=r.alloc(0x1000);session=r.alloc(0x100);player=r.alloc(0x900)
r.write(runtime+0xc8,struct.pack('<Q',session));r.write(session+0xa0,struct.pack('<Q',player))
r.write(r.base+0x4817e70,struct.pack('<Q',runtime))
observations=[]
def acknowledged(uc,address,size,user):
    assert uc.reg_read(UC_X86_REG_RDX)==0xa8f;r.finish_shim(0)
def success(uc,address,size,user):
    value=uc.reg_read(UC_X86_REG_RDX)&0xffffffff
    r.finish_shim(1 if value==0 else 0)
def apply_inventory(uc,address,size,user):
    assert uc.reg_read(UC_X86_REG_RCX)==player+0x440 and uc.reg_read(UC_X86_REG_R8)==0
    vector=uc.reg_read(UC_X86_REG_RDX);begin,end=struct.unpack('<QQ',r.read(vector,16))
    assert end-begin==0x408
    observations.append(dict(uid=struct.unpack('<Q',r.read(begin,8))[0],group=r.read(begin+8,1)[0],
        slot=struct.unpack('<h',r.read(begin+9,2))[0],template=struct.unpack('<i',r.read(begin+0xb,4))[0],
        count=struct.unpack('<i',r.read(begin+0x10,4))[0]))
    r.finish_shim(0)
def closed_ui(uc,address,size,user):r.finish_shim(0)
for rva,fn in ((0x74ffa0,acknowledged),(0x751120,success),(0x197dad0,apply_inventory),(0x4ab640,closed_ui)):
    r.uc.hook_add(UC_HOOK_CODE,fn,begin=r.base+rva,end=r.base+rva)
updated=profile(11300,{0:10,1:10,2:10})
item=dict(uid=1001040,template=714108,metadata=2,group=4,slot=3,count=1)
raw=reset_ack(mount=dict(uid=1001011,racing=updated),removed=item).payload
data=r.alloc(len(raw));r.write(data,raw);buffer=r.alloc(48)
r.write(buffer+8,struct.pack('<QQQ',data,data+len(raw),data+len(raw)))
r.write(r.stack+0x20,struct.pack('<Q',buffer));ui=r.alloc(0x400)
assert r.call(0x30245d0,ui,0,0,0)&255==1
assert int.from_bytes(r.read(buffer+32,4),'little')==len(raw)
assert read(r,mounts)==dict(uid=1001011,unknown=0,**updated)
assert read(r,mounts+0x80)==dict(uid=1001012,unknown=0,**initial)
assert observations==[dict(uid=0,group=4,slot=3,template=0,count=0)]
failure=reset_ack(-1).payload;data2=r.alloc(len(failure));r.write(data2,failure);buffer2=r.alloc(48)
r.write(buffer2+8,struct.pack('<QQQ',data2,data2+len(failure),data2+len(failure)))
r.write(r.stack+0x20,struct.pack('<Q',buffer2))
assert r.call(0x30245d0,ui,0,0,0)&255==1
assert int.from_bytes(r.read(buffer2+32,4),'little')==len(failure)
assert len(observations)==1 and read(r,mounts)==dict(uid=1001011,unknown=0,**updated)
out=dict(ok=True,image_sha256=IMAGE_SHA,receiver='30245D0',inventory_reader='DD46E0/DAEE20',
    full_receiver_returned=True,consumed=len(raw),target=read(r,mounts),foreign=read(r,mounts+0x80),
    inventory_application_observed=observations,inventory_apply_function_executed=False,UI_closed=True,
    acknowledgement_service_stubbed=True,failure_reply_consumed=len(failure),failure_unchanged=True,private_Unicorn=True,live_process=False,natural_GUI=False,
    original_EXE_KOM_modified=False,source_sha256=hashlib.sha256((R/'els_server/protocol/mount_messages.py').read_bytes()).hexdigest())
(W/'native-reset-consumer.json').write_bytes((json.dumps(out,indent=2)+'\n').encode());print(json.dumps(out))
