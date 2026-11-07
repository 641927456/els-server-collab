"""Execute original7E0 writer in private Unicorn memory, without a client."""
from pathlib import Path
import json,struct,sys,time,traceback
R=Path('G:/els');F=Path(__file__).resolve().parent;sys.path.insert(0,str(R/'tools'))
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_RSP,UC_X86_REG_RIP,UC_X86_REG_RAX

class Native(Replay):
    def call6(self,rva,args):
        sp=self.stack-8;self.write(sp,struct.pack('<Q',self.stop))
        for i,value in enumerate(args[4:]):self.write(sp+0x28+i*8,struct.pack('<Q',value))
        for reg,value in zip((UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9),args):self.uc.reg_write(reg,value)
        self.uc.reg_write(UC_X86_REG_RSP,sp);self.uc.emu_start(self.base+rva,self.stop,count=1000000)
        assert self.uc.reg_read(UC_X86_REG_RIP)==self.stop
    def pointer(self,p,value):self.write(p,struct.pack('<Q',value))
    def u64(self,p):return int.from_bytes(self.read(p,8),'little')

report=dict(ok=False,image_sha256=IMAGE_SHA,original_writer_RVA='3278F90',native_Game=False,
    live_process_access=False,original_client_changes=0,natural_GUI=False,
    seams=['sequence supplied by private vtable fixture','transport send captured after original serialization'])
try:
    replay=Native();context=replay.alloc(0x130);vtable=replay.alloc(0x60);seq=replay.alloc(16)
    replay.write(seq,b'\xb8\x01\0\0\0\xc3');replay.pointer(vtable+0x50,seq);replay.pointer(context,vtable)
    wire=[]
    def send(uc,address,size,user):
        event=uc.reg_read(UC_X86_REG_RDX);begin=replay.u64(event+0x3e);end=replay.u64(event+0x46)
        wire.append(dict(event_id=int.from_bytes(replay.read(event+0x10,4),'little'),
            kind=int.from_bytes(replay.read(event+0x34,2),'little'),payload_hex=replay.read(begin,end-begin).hex()))
        replay.finish_shim(1)
    replay.uc.hook_add(UC_HOOK_CODE,send,begin=replay.base+0x682d80,end=replay.base+0x682d80)
    body=replay.alloc(1)
    for value in(0,1):
        replay.write(body,bytes([value]));replay.call6(0x3278f90,(context,0,0,0,0,body))
    assert wire==[dict(event_id=0x202,kind=0x7e0,payload_hex=bytes([v]).hex())for v in(0,1)]
    report.update(ok=True,events=wire,source_identity='Native key dispatch B8AEA0 ->324C410 ->3278F90;324C410 sends NOT(FEC210 current displayed actor) and waits7E1')
except BaseException:
    report['error']=traceback.format_exc()
    if 'replay'in globals():report['failure_RVA']=hex(replay.uc.reg_read(UC_X86_REG_RIP)-replay.base)
p=F/('native-toggle-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False));raise SystemExit(not report['ok'])
