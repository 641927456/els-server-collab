"""Execute pinned 2EC8DE0, including its actual event kind and map writer."""
import bootstrap,json,struct
from verify_fixed_cubes_native import CubeReplay
from role_native_replay import IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RSP,UC_X86_REG_RBP,UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_RIP
from els_server.protocol.protocol_codec import Event
from els_server.protocol.modern_ice_messages import withdraw_request

class NativeWithdrawal:
 def __init__(self):
  self.r=CubeReplay();r=self.r
  self.session=r.alloc(0x130);vtable=r.alloc(0x60);callback=r.alloc(16)
  r.write(vtable+0x50,struct.pack('<Q',callback));r.write(self.session,struct.pack('<Q',vtable));r.write(self.session+0x118,struct.pack('<I',17))
  def sequence(uc,address,size,user):
   assert uc.reg_read(UC_X86_REG_RDX)==0xbd3
   r.finish_shim(1)
  r.uc.hook_add(UC_HOOK_CODE,sequence,begin=callback,end=callback)
 def event(self,rows):
  r=self.r;rows=tuple(sorted(rows));assert 1<=len(rows)<=10 and len({uid for uid,_ in rows})==len(rows)
  head=r.alloc(48);nodes=[r.alloc(48)for _ in rows];mapping=r.alloc(16)
  def tree(lo,hi,parent):
   if lo>=hi:return head
   mid=(lo+hi)//2;p=nodes[mid];left=tree(lo,mid,p);right=tree(mid+1,hi,p)
   r.write(p,struct.pack('<QQQH',left,parent,right,0));r.write(p+0x20,struct.pack('<Qi',*rows[mid]));return p
  root=tree(0,len(rows),head);r.write(head,struct.pack('<QQQH',nodes[0],root,nodes[-1],0x101));r.write(mapping,struct.pack('<QQ',head,len(rows)))
  sp=r.stack-8;r.write(sp,struct.pack('<Q',r.stop));r.write(sp+0x30,struct.pack('<Q',mapping))
  r.uc.reg_write(UC_X86_REG_RSP,sp);r.uc.reg_write(UC_X86_REG_RCX,self.session)
  r.uc.emu_start(r.base+0x2ec8de0,r.base+0x2ec90a1,count=1000000)
  assert r.uc.reg_read(UC_X86_REG_RIP)==r.base+0x2ec90a1
  bp=r.uc.reg_read(UC_X86_REG_RBP);event_id=struct.unpack('<I',r.read(bp-0x59,4))[0];kind=struct.unpack('<H',r.read(bp-0x35,2))[0]
  uid=struct.unpack('<Q',r.read(bp-0x45,8))[0];target=struct.unpack('<Q',r.read(bp-0x3d,8))[0];mode=r.read(bp-0x33,1)[0]
  begin,end,_=struct.unpack('<QQQ',r.read(bp-0x2b,24));payload=r.read(begin,end-begin)
  assert (event_id,kind,uid,target,mode)==(0x202,0xbd3,2**64-1,2**64-1,0)
  assert withdraw_request(payload)==rows
  # The destination performer list is constructed by the original sender.
  count=struct.unpack('<Q',r.read(bp-0x4d,8))[0];assert count==1
  return Event(event_id,kind=kind,payload=payload,uid=uid,target_uid=target,payload_mode=mode,performers=(0,))

if __name__=='__main__':
 native=NativeWithdrawal();cases=[]
 for rows in(((1300001,1),),((1300003,7),(1300001,1),(1300002,2))):
  event=native.event(rows);cases.append(dict(kind=event.kind,rows=withdraw_request(event.payload),payload_hex=event.payload.hex()))
 out=dict(passed=True,image_sha256=IMAGE_SHA,sender='0x2ec8de0',network_boundary='0x2ec90a1',cases=cases,natural_GUI=False,callbacks_simulated=['Session sequence getter'],old_tests_only_exercised_map_writer=True)
 (bootstrap.HERE/'native-request-proof.json').write_text(json.dumps(out,indent=2)+'\n','utf8');print(json.dumps(out))
