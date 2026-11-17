"""Original complete Eve carry selector; observe its position-service calls."""
from pathlib import Path
import sys,struct,json
ROOT=Path('G:/els');W=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
from seal_quest_resources import ResourceReplay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_GS_BASE
r=ResourceReplay();game=r.alloc(0x1800);owner=r.alloc(0x1e000)
r.write(game,struct.pack('<Q',r.base+0x41bfd28));r.write(owner,struct.pack('<Q',r.base+0x4233af0))
uid=1002;r.write(owner+0x3d0,struct.pack('<Q',uid));r.write(owner+0x197f8,struct.pack('<3f',125.,50.,10.));r.write(owner+0x19812,b'\x01')
# A ready TLS registry containing the original game weak handle. Native
# 1528F0/15A100 and game/owner getters execute unchanged.
teb=r.uc.reg_read(UC_X86_REG_GS_BASE);tls_array=r.alloc(8);tls=r.alloc(16)
r.write(teb+0x58,struct.pack('<Q',tls_array));r.write(tls_array,struct.pack('<Q',tls));r.write(tls+8,struct.pack('<I',0x7fffffff))
registry=r.alloc(24);entry=r.alloc(32);r.write(registry,struct.pack('<QQ',entry,entry+32))
r.write(entry,struct.pack('<Q',game));r.write(entry+0xc,struct.pack('<II',1,1))
r.write(r.base+0x4816340,struct.pack('<Q',registry));r.write(r.base+0x48162ac,bytes(4));r.write(r.base+0x478cb88,struct.pack('<ii',0,1))
actors=[];labels={}
def actor(label,template,actor_uid,hp,kind=1):
    p=r.alloc(0x1b800);definition=r.alloc(4);control=r.alloc(0xb0)
    r.write(p+0x3c4,struct.pack('<i',kind));r.write(definition,struct.pack('<i',template));r.write(p+0x19e20,struct.pack('<Q',definition))
    r.write(p+0x18cf0,struct.pack('<Q',control));r.write(control+0x44,struct.pack('<i',1));r.write(control+0xa8,struct.pack('<Q',actor_uid))
    holder=r.alloc(0x48);value=r.alloc(0x20);r.write(p+0x1410,struct.pack('<Q',holder));r.write(holder+0x40,struct.pack('<Q',value))
    r.write(value+0x10,struct.pack('<I',((value+8)&0xffffffff)^struct.unpack('<I',struct.pack('<f',hp))[0]))
    actors.append(p);labels[p]=label;return p
actor('owned384',384,uid,100.);actor('foreign384',384,uid+1,100.);actor('dead384',384,uid,0.)
actor('owned519',519,uid,100.);actor('playerKind',384,uid,100.,kind=0)
vector=r.alloc(len(actors)*8);r.write(vector,b''.join(struct.pack('<Q',p)for p in actors));r.write(game+0x348,struct.pack('<QQ',vector,vector+len(actors)*8))
calls=[]
def relocation(uc,address,size,user):
    p=uc.reg_read(UC_X86_REG_RCX);position=uc.reg_read(UC_X86_REG_RDX);facing=uc.reg_read(UC_X86_REG_R8)&255
    calls.append(dict(actor=labels[p],position=struct.unpack('<3f',r.read(position,12)),facing=facing))
    r.finish_shim(0)
hook=r.uc.hook_add(UC_HOOK_CODE,relocation,begin=r.base+0x15710e0,end=r.base+0x15710e0)
cases=[]
try:
    for template,expected in [(0,['owned384','owned519']),(384,['owned384'])]:
        calls.clear();before={p:r.read(p,0x1b800)for p in actors};owner_before=r.read(owner,0x1e000)
        r.call(0x200c720,owner,template)
        assert [v['actor']for v in calls]==expected,calls
        assert all(v['position']==(125.,50.,10.)and v['facing']==1 for v in calls)
        assert r.read(owner,0x1e000)==owner_before and all(r.read(p,0x1b800)==b for p,b in before.items())
        cases.append(dict(filter=template,calls=list(calls),owner_and_actor_storage_unchanged=True))
finally:r.uc.hook_del(hook)
out=dict(image_sha256=IMAGE_SHA,function='200C720',binding='Eve primary v14F8; 1041040 invokes it with0 after BD',
    original_getters_executed=True,position_service='15710E0 (observed, not executed)',cases=cases,
    full_selector_returned=True,original_image_unchanged=True,natural_GUI=False,live_process=False)
(W/'native-sentry-relocation.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
