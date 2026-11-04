"""Original 559/196 senders in private Unicorn memory; no live process."""
import bootstrap,struct
from verify_fixed_cubes_native import CubeReplay
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_RSP,UC_X86_REG_RIP
from els_server.protocol.protocol_codec import Event

class NativeRequests:
 def __init__(self):
  r=self.r=CubeReplay();self.session=r.alloc(0x130);vt=r.alloc(0x60);seq=r.alloc(16)
  r.write(vt+0x50,struct.pack('<Q',seq));r.write(self.session,struct.pack('<Q',vt));r.write(self.session+0x118,struct.pack('<I',17))
  r.uc.hook_add(UC_HOOK_CODE,lambda *a:r.finish_shim(1),begin=seq,end=seq)
 def send(self,entry,dto):
  r=self.r;sp=r.stack-8;r.write(sp,struct.pack('<Q',r.stop));r.write(sp+0x30,struct.pack('<Q',dto))
  r.uc.reg_write(UC_X86_REG_RSP,sp);r.uc.reg_write(UC_X86_REG_RCX,self.session)
  r.uc.emu_start(r.base+entry,r.base+0x682d80,count=1000000)
  assert r.uc.reg_read(UC_X86_REG_RIP)==r.base+0x682d80
  e=r.uc.reg_read(UC_X86_REG_RDX);kind=struct.unpack('<H',r.read(e+0x34,2))[0]
  begin,end,_=struct.unpack('<QQQ',r.read(e+0x3e,24));uid,target=struct.unpack('<QQ',r.read(e+0x24,16))
  assert(uid,target,r.read(e+0x36,1)[0])==(2**64-1,2**64-1,0)
  return Event(0x202,kind=kind,payload=r.read(begin,end-begin),performers=(0,))
 def preview(self,template,minor=0):
  r=self.r;p=r.alloc(30);keys=r.alloc(4);r.write(keys,bytes(4))
  r.write(p,struct.pack('<iQQQBB',template,keys,keys+4,keys+4,minor,0))
  return self.send(0x2353800,p)
 def use(self,uid,option=1,minor=0):
  r=self.r;p=r.alloc(31);head=r.alloc(32)
  r.write(head,struct.pack('<QQQH',head,head,head,0x101))
  r.write(p,struct.pack('<QBBBQQi',uid,0,minor,0,head,0,option))
  return self.send(0x2353c10,p)
