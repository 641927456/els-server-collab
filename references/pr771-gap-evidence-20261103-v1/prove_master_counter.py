"""Original GUI arithmetic only; controlled UI objects, no combat/clear claim."""
from pathlib import Path
import sys,struct,json,hashlib
ROOT=Path('G:/els');W=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import *

r=Replay();actor=r.alloc(0x1c000);ui=r.alloc(0x200);holder=r.alloc(8)
r.write(holder,struct.pack('<Q',actor+0x278));r.write(ui+0xe8,struct.pack('<QQ',0,4*64))
def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]
def xmm(reg,value):r.uc.reg_write(reg,int.from_bytes(struct.pack('<f',value)+bytes(12),'little'))
def block(start,end):
    def checked(uc,address,size,user):
        if not r.base+start<=address<r.base+end:raise ValueError('Unexpected control flow')
    hook=r.uc.hook_add(UC_HOOK_CODE,checked)
    try:r.uc.emu_start(r.base+start,r.base+end,count=10000)
    finally:r.uc.hook_del(hook)
    assert r.uc.reg_read(UC_X86_REG_RIP)==r.base+end
def counter(maxhp,hp,number,extra):
    r.write(actor+0x1b564,struct.pack('<f',hp));r.write(actor+0x1b2d0,struct.pack('<i',extra));r.write(ui+0xc0,struct.pack('<H',number))
    r.write(r.stack-0x400,bytes(0x400));r.uc.reg_write(UC_X86_REG_RSP,r.stack-0x200)
    for reg,value in [(UC_X86_REG_RCX,actor),(UC_X86_REG_RDI,holder),(UC_X86_REG_RSI,ui),(UC_X86_REG_R14,0),(UC_X86_REG_R8,number)]:r.uc.reg_write(reg,value)
    xmm(UC_X86_REG_XMM8,maxhp)
    block(0x1a635aa,0x1a63704)
    whole=r.uc.reg_read(UC_X86_REG_R15)&0xffffffff
    r.uc.reg_write(UC_X86_REG_R13,extra);xmm(UC_X86_REG_XMM9,0);xmm(UC_X86_REG_XMM10,hp)
    block(0x1a63b3a,0x1a63b84)
    return dict(max_hp=maxhp,hp=hp,number=number,extra=extra,whole=whole,display_counter=r.uc.reg_read(UC_X86_REG_RDI)&0xffff)
cases=[]
for maxhp in (100000.0,1866516480.0):
    for fraction,extra,expected in [(1.,150,300),(.001,150,151),(.001,0,1),(0.,0,0)]:
        row=counter(maxhp,f32(maxhp*fraction),150,extra);assert row['display_counter']==expected,row;cases.append(row)
out=dict(image_sha256=IMAGE_SHA,original_function='1A634A0',arithmetic_ranges=['1A635AA..1A63704','1A63B3A..1A63B84'],
    fields=dict(current_hp='actor+1B564',extra_count='actor+1B2D0',ui_gage_count='ui+C0'),
    cases=cases,original_image_unchanged=True,controlled_UI_fixture=True,natural_boss_kill_tested=False,
    limitation='Arithmetic consumer verified; no claim that these fixtures reproduce the live actor state or a full GUI frame.')
(W/'native-master-counter.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out))
