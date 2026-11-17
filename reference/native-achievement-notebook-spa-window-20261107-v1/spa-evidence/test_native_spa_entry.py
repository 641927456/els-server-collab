"""Original Phoru consumer and click producer in isolated Unicorn memory.

Network/UI terminal calls are explicit seams; original parsing, map lookup,
one-item click construction and EA serialization execute unchanged.
"""
from qa_environment import F,R
import hashlib,json,struct,sys,time,traceback
from els_server.protocol.npc_trade_messages import purchase_request
sys.path.insert(0,str(R/'tools'))
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_RSP,UC_X86_REG_RIP,UC_X86_REG_RAX

report=dict(ok=False,image_sha256=IMAGE_SHA,live_process_access=False,client_changes=0,
 natural_GUI=False,seams=['terminal store-state setter captured without rendering',
 'wait-indicator UI call omitted','network facade captured after click construction',
 'transport send captured after native serialization','sequence source supplied'])

class SpaReplay(Replay):
    def hook(self,rva,callback):
        self.uc.hook_add(UC_HOOK_CODE,callback,begin=self.base+rva,end=self.base+rva)
    def call5(self,rva,args):
        sp=self.stack-8;self.write(sp,struct.pack('<Q',self.stop))
        for i,value in enumerate(args[4:]):self.write(sp+0x28+i*8,struct.pack('<Q',value))
        for reg,value in zip((UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9),args):self.uc.reg_write(reg,value)
        self.uc.reg_write(UC_X86_REG_RSP,sp);self.uc.emu_start(self.base+rva,self.stop,count=1000000)
        if self.uc.reg_read(UC_X86_REG_RIP)!=self.stop:raise ValueError('Replay instruction bound')
        return self.uc.reg_read(UC_X86_REG_RAX)
    def u64(self,p):return int.from_bytes(self.read(p,8),'little')
    def i32(self,p):return int.from_bytes(self.read(p,4),'little',signed=True)
    def ptr(self,p,value):self.write(p,struct.pack('<Q',value))
    def buffer(self,wire):
        data=self.alloc(len(wire));self.write(data,wire);buf=self.alloc(48)
        self.write(buf+8,struct.pack('<QQQ',data,data+len(wire),data+len(wire)))
        return buf

try:
    replay=SpaReplay();actor=replay.alloc(0xf00)
    # 21577E6's RIP-relative operand resolves to the NPC manager at4817E58;
    # 4817E50 is the separate request/wait context, used by the click method.
    replay.ptr(replay.base+0x4817e58,actor)
    replay.ptr(replay.base+0x4817e50,replay.alloc(0x900))
    seen=[]
    def state(uc,address,size,user):
        seen.append((uc.reg_read(UC_X86_REG_RCX),uc.reg_read(UC_X86_REG_RDX)&0xffffffff));replay.finish_shim(1)
    replay.hook(0x21653f0,state)
    for value in (0,2,3):
        buf=replay.buffer(struct.pack('>i',value))
        replay.call5(0x21577b0,(0,0,0,0xc3a,buf))
        assert seen[-1]==(actor,value) and replay.i32(buf+32)==4
    report['state_consumer']=dict(RVA='21577B0',kind='C3A',payload='BEi32 state',values=[v for _,v in seen],consumed=4)
    root=replay.alloc(0x1300);world=replay.alloc(0x100);manager=replay.alloc(0x90)
    replay.ptr(replay.base+0x4817e70,root);replay.ptr(root+0x490,world);replay.ptr(root+0x1230,manager)
    replay.write(world+0x68,struct.pack('<i',1500))
    head=replay.alloc(0x28);node=replay.alloc(0x28)
    replay.write(head,struct.pack('<QQQBB',node,node,node,1,1))
    replay.write(node,struct.pack('<QQQBB2xiii',head,head,head,0,0,1500,10196,710012))
    replay.ptr(manager+0x60,head)
    replay.hook(0x1b651f0,lambda *args:replay.finish_shim(0))
    replay.hook(0x74fb70,lambda *args:replay.finish_shim(0))
    constructed=[]
    def purchase(uc,address,size,user):
        value=uc.reg_read(UC_X86_REG_R8);tree=replay.u64(value+3);n=replay.u64(tree+8)
        constructed.append(dict(flag=replay.read(value,1)[0],mode=int.from_bytes(replay.read(value+1,2),'little'),
            entries=[(replay.i32(n+0x1c),replay.i32(n+0x20))],merchant=replay.i32(value+0x13)))
        replay.finish_shim(1)
    replay.hook(0x7b4870,purchase)
    replay.call(0x1a29dc0,actor)
    assert constructed==[dict(flag=0,mode=0,entries=[(710012,1)],merchant=10196)]
    report['click_producer']=dict(RVA='1A29DC0',native_facade_RVA='7B4870',map=1500,constructed=constructed[0])
    # Serialize the exact native in-memory tree shape produced above. This
    # runs the original EA writer, not a Python reconstruction of its bytes.
    tree=replay.alloc(0x28);n=replay.alloc(0x28)
    replay.write(tree,struct.pack('<QQQBB',n,n,n,1,1))
    replay.write(n,struct.pack('<QQQBB2xii',tree,tree,tree,0,0,710012,1))
    body=replay.alloc(0x20);replay.write(body,struct.pack('<BHQQi',0,0,tree,1,10196))
    context=replay.alloc(0x130);vtable=replay.alloc(0x60);seq=replay.alloc(16)
    replay.write(seq,b'\xb8\x01\0\0\0\xc3');replay.ptr(vtable+0x50,seq);replay.ptr(context,vtable)
    wire=[]
    def send(uc,address,size,user):
        event=uc.reg_read(UC_X86_REG_RDX);begin=replay.u64(event+0x3e);end=replay.u64(event+0x46)
        wire.append(dict(event_id=replay.i32(event+0x10),kind=int.from_bytes(replay.read(event+0x34,2),'little'),payload=replay.read(begin,end-begin)))
        replay.finish_shim(1)
    replay.hook(0x682d80,send)
    replay.call5(0x7bcca0,(context,0,0,0,0,body))
    assert len(wire)==1
    event=wire[0];assert(event['event_id'],event['kind'])==(0x202,0xea)
    entries,merchant=purchase_request(event['payload'])
    assert(entries,merchant)==([(710012,1)],10196)
    report['native_EA_writer']=dict(RVA='7BCCA0',event_id=event['event_id'],kind=hex(event['kind']),payload_hex=event['payload'].hex(),entries=entries,merchant=merchant)
    report['ok']=True
except BaseException:
    report['failure']=traceback.format_exc()
    if 'replay'in globals():report['failure_RVA']=hex(replay.uc.reg_read(UC_X86_REG_RIP)-replay.base)
p=F/('native-entry-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False));raise SystemExit(not report['ok'])
