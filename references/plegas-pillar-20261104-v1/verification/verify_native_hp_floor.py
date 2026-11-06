"""Execute the original native HP delta/clamp block in private memory."""
from pathlib import Path
import json,sys,struct
R=Path('G:/els');O=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'tools'))
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_XMM1,UC_X86_REG_XMM2,UC_X86_REG_RSP,UC_X86_REG_RIP
r=Replay();g=r.alloc(0x80);result=[]
def bits(f):return struct.unpack('<I',struct.pack('<f',f))[0]
def done(uc,a,size,user):
 sp=uc.reg_read(UC_X86_REG_RSP);result.append(struct.unpack('<f',r.read(sp+0x48,4))[0]);uc.reg_write(UC_X86_REG_RIP,r.stop);uc.emu_stop()
r.uc.hook_add(UC_HOOK_CODE,done,begin=r.base+0x1272dc4,end=r.base+0x1272dc4)
rows=[]
for hp,delta,floor,expected in ((120835.,-999999.,0.,0.),(120835.,-999999.,1.,1.),(120835.,-100.,1.,120735.),(1.,-999999.,1.,1.),(1.,-999999.,0.,0.),(1.,30.,1.,31.)):
 r.write(g,bytes(0x80));r.write(g+0x10,struct.pack('<I',bits(hp)^(g+8)&0xffffffff));r.write(g+0x28,struct.pack('<I',bits(120835.)^(g+0x20)&0xffffffff));r.uc.reg_write(UC_X86_REG_XMM1,bits(delta));r.uc.reg_write(UC_X86_REG_XMM2,bits(floor));r.call(0x1272cf0,g)
 assert result[-1]==expected,(hp,delta,floor,result[-1]);rows.append(dict(hp=hp,delta=delta,native_floor=floor,result=result[-1]))
v=dict(ok=True,image_sha256=IMAGE_SHA,original_block='1272CF0..1272DC4',scope='Original float arithmetic, max clamp and caller-supplied min clamp; stops before unrelated TLS scalar commit bookkeeping',cases=rows,no_game_process=True)
(O/'native-hp-floor-proof.json').write_text(json.dumps(v,indent=2)+'\n','utf8');print(json.dumps(v))
