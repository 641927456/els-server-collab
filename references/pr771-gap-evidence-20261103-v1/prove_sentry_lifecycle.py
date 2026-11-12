"""Original arithmetic/selection blocks, not a full actor or stage replay."""
from pathlib import Path
import struct,sys,json
ROOT=Path('G:/els');W=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import *
r=Replay();owner=r.alloc(0x1e000);effect=r.alloc(8);vt=r.alloc(0x1b40);r.write(owner,struct.pack('<Q',vt))
def run(start,stops,allowed):
    def checked(uc,address,size,user):
        if address-r.base in stops:uc.emu_stop();return
        if not allowed[0]<=address-r.base<allowed[1]:raise ValueError('Unexpected control flow')
    hook=r.uc.hook_add(UC_HOOK_CODE,checked)
    try:r.uc.emu_start(r.base+start,r.stop,count=10000)
    finally:r.uc.hook_del(hook)
    rip=r.uc.reg_read(UC_X86_REG_RIP)-r.base;assert rip in stops;return rip
times=[]
for skill,rate,extra,expected in [(25000,1.,0.,20.),(25030,1.,0.,60.),(25000,1.5,5.,35.),(25030,1.5,5.,95.)]:
    r.write(owner+0x1d14c,struct.pack('<f',rate));r.write(owner+0x7bc0,struct.pack('<f',extra))
    for reg,value in [(UC_X86_REG_R13,owner),(UC_X86_REG_RBX,effect),(UC_X86_REG_RBP,r.stack-0x200),(UC_X86_REG_RAX,skill)]:r.uc.reg_write(reg,value)
    run(0x200b867,{0x200b8a5},(0x200b867,0x200b8a9))
    value=struct.unpack('<f',r.read(r.stack-0x280,4))[0];assert value==expected
    times.append(dict(skill=skill,rate=rate,extra=extra,computed_duration=value))
selections=[]
for ids,expected in [([],True),([410],False),([411],True),([None,410],False),([411,410],False)]:
    ptrs=[]
    for template in ids:
        buff=r.alloc(0x58)if template is not None else 0
        if buff:r.write(buff+0x50,struct.pack('<i',template))
        ptrs.append(buff)
    vector=r.alloc(max(8,len(ptrs)*8));r.write(vector,b''.join(struct.pack('<Q',v)for v in ptrs))
    r.write(owner+0x1858,struct.pack('<QQ',vector,vector+8*len(ptrs)));r.uc.reg_write(UC_X86_REG_RSI,owner)
    rip=run(0x1feac62,{0x1feac9c,0x1feacb3},(0x1feac62,0x1feacb3))
    selected=rip==0x1feac9c;assert selected==expected
    target=r.uc.reg_read(UC_X86_REG_RDX)if selected else None
    assert target in (None,384)
    selections.append(dict(buff_templates=ids,cleanup_selected=selected,target=target))
assert struct.unpack('<Q',r.read(r.base+0x4233af0+0x1b38,8))[0]==r.base+0x200c170
out=dict(image_sha256=IMAGE_SHA,arithmetic_range='200B867..200B8A5',selection_range='1FEAC62..1FEACB3',
    virtual_binding='CX2Eve primary 4233AF0 + 1B38 -> 200C170',times=times,selections=selections,
    original_image_unchanged=True,cleanup_called=False,full_actor_update=False,stage_continuity_tested=False)
(W/'native-sentry-lifecycle.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
