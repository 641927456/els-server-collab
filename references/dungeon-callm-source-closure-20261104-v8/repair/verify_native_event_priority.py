"""Original condition constructor, RATE dispatch and state-change loop guard."""
import hashlib,json,os,struct,sys
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[3];sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tools/pylibs')];os.environ['ELS_RUNTIME_IMAGE']=str(ROOT/'analysis/client-6c6b5180/x2-runtime.bin')
from role_native_replay import Replay,IMAGE_SHA
from runtime_queries import b,base,owner
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_R12,UC_X86_REG_R13,UC_X86_REG_R14,UC_X86_REG_RSI,UC_X86_REG_RBX
r=Replay();uc=r.uc;condition=r.alloc(0x478+16);r.write(condition,b'\x55'*(0x478+16));assert r.call(0x19e3070,condition)==condition
assert r.read(condition+0x478,16)==b'\x55'*16
assert struct.unpack('<i',r.read(condition+0x14,4))[0]==-1 and struct.unpack('<i',r.read(condition+0x44,4))[0]==-1
assert r.read(condition,1)==bytes(1)
actor=r.alloc(0x1d000);aux=r.alloc(0x100);event=r.alloc(0x30);r.write(event+4,b'\1');uc.reg_write(UC_X86_REG_R12,event);r.write(actor+0x19e28,struct.pack('<Q',aux));r.write(aux+0xb8,bytes(16))
ends={base+0x16bd368:'direct_state_change',base+0x16bec02:'no_rate_transition',base+0x16bec76:'stop_event_loop',base+0x16bec13:'continue_event_loop'};seen=[]
def stop(uc,address,size,user):seen.append(ends[address]);uc.emu_stop()
hooks=[uc.hook_add(UC_HOOK_CODE,stop,begin=p,end=p)for p in ends]
rates=[]
for rate,expected in[(100,'direct_state_change'),(0,'no_rate_transition')]:
 for mode in(0,1):
  r.write(condition+0x14,struct.pack('<i',rate));uc.reg_write(UC_X86_REG_R13,condition);uc.reg_write(UC_X86_REG_R14,mode);uc.reg_write(UC_X86_REG_RSI,actor);seen.clear();uc.emu_start(base+0x16bea39,base+0x16bec77,count=80);assert seen==[expected],(rate,mode,seen);rates.append(dict(rate=rate,condition_mode=mode,native_path=seen[0]))
for hook in hooks:uc.hook_del(hook)
ends={base+0x16bec76:'stop_event_loop',base+0x16bec13:'continue_event_loop'};hooks=[uc.hook_add(UC_HOOK_CODE,stop,begin=p,end=p)for p in ends];loops=[]
for counter in range(16):
 current=0xa0|counter;r.write(actor+0x19c00,bytes([current]));r.write(actor+0x19b7c,bytes([current]));uc.reg_write(UC_X86_REG_RBX,actor)
 uc.emu_start(base+0x1694ad2,base+0x1694af8,count=20);updated=r.read(actor+0x19b7c,1)[0];assert updated==0xa0|((counter+1)&15)
 uc.reg_write(UC_X86_REG_RSI,actor);seen.clear();uc.emu_start(base+0x16bec02,base+0x16bec77,count=10);assert seen==['stop_event_loop'];loops.append(dict(counter=counter,after_success=seen[0]))
 r.write(actor+0x19b7c,bytes([current]));seen.clear();uc.emu_start(base+0x16bec02,base+0x16bec77,count=10);assert seen==['continue_event_loop']
blocks=[(0x19e3070,0x19e36f9),(0x16bea39,0x16bea5a),(0x1694ad2,0x1694af8),(0x16bec02,0x16bec13),(0x1614952,0x16149ea)]
out=dict(ok=True,image_sha256=IMAGE_SHA,scope='Unmodified native instruction blocks only; no full actor or natural-combat simulation',condition_constructor_rva='0x19e3070',condition_rate_field='0x14',rate_dispatch= rates,state_change_commit_rva='0x1694ad2',event_loop_guard_rva='0x16bec02',successful_change_stops_before_next_event=loops,unchanged_counter_negative_cases=16,original_loader_numeric_index_sequence=dict(start=1,next='increment by one',vector_element='index minus one',rva='0x1614952-0x16149ea'),code_sha256={hex(a)+'-'+hex(z):hashlib.sha256(b[a:z]).hexdigest()for a,z in blocks},original_client_modified=False,client_processes=0)
(W/'native-event-priority-tests.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(ok=True,rate_cases=len(rates),counter_success_cases=len(loops),counter_negative_cases=16,constructor_preserved_adjacent_memory=True)))
