"""Original cold DB6E10 and890 parse, stopping before native UI mutation."""
from pathlib import Path
import hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent;B=W/'test-source-v1'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
from els_server.protocol import relationship_messages as wire
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
import runtime_queries as q
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RIP,UC_X86_REG_RAX
report=dict(ok=False,image_sha256=IMAGE_SHA,native_Game=False,natural_GUI=False,cases=[])
try:
    r=Replay()
    r.uc.hook_add(UC_HOOK_CODE,lambda uc,a,n,u:r.finish_shim(uc.reg_read(UC_X86_REG_RAX)),begin=r.base+0x3ae43c0,end=r.base+0x3ae43c0)
    state=dict(pair_id='owned',kind=2,peer_uid=1002,peer_name='已婚伴侣',created_at=1793920000,refreshed_at=1793923600)
    raw=wire.cold(state);out=r.alloc(0x65);reader,buffer=stream(r,raw)
    # Both native strings need their ordinary small-string constructor state.
    r.write(out+9+24,struct.pack('<Q',7));r.write(out+0x29+24,struct.pack('<Q',7))
    r.call(0xdb6e10,reader,out)
    assert int.from_bytes(r.read(buffer+32,4),'little')==len(raw)
    assert r.read(out,1)==b'\2'and struct.unpack('<Q',r.read(out+1,8))[0]==1002
    assert struct.unpack('<Q',r.read(out+0x49,8))[0]==state['created_at']
    assert struct.unpack('<Q',r.read(out+0x5a,8))[0]==state['refreshed_at']
    report['cases'].append(dict(original_cold_reader='0xdb6e10',kind=2,first_and_refresh_distinct=True,bytes=len(raw)))
    entry=0xd348d0;md=q.capstone.Cs(q.capstone.CS_ARCH_X86,q.capstone.CS_MODE_64);instructions=[]
    for segment in q.groups[entry]:instructions+=list(md.disasm_lite(q.b[segment[0]:segment[1]],q.base+segment[0]))
    stop=next(pc+size for pc,size,op,args in instructions if op=='call'and args==hex(r.base+0x3b6d160))
    r.uc.hook_add(UC_HOOK_CODE,lambda uc,a,n,u:uc.reg_write(UC_X86_REG_RIP,r.stop),begin=stop,end=stop)
    raw=wire.married(state).payload;_,buffer=stream(r,raw);r.write(r.stack+0x20,struct.pack('<Q',buffer))
    r.call(entry,r.alloc(0x800),0,0,0x890)
    assert int.from_bytes(r.read(buffer+32,4),'little')==len(raw)
    report['cases'].append(dict(original890_full_read_prefix=hex(entry),bytes=len(raw),stopped_before_UI=True,ceremony_and_refresh_flags=False))
    report.update(ok=True,wire_readers_unmodified=True,protocol_sha256=hashlib.sha256(Path(wire.__file__).read_bytes()).hexdigest())
except BaseException:
    report['error']=traceback.format_exc()
    if 'r'in locals():report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=W/('native-marriage-state-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));raise SystemExit(not report['ok'])
