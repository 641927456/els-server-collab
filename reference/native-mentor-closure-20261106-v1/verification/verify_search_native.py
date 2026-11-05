"""Run716's original consumer through its wire reader, stopping before UI globals."""
from pathlib import Path
import hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
B=R/'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
import els_server,els_server.protocol
els_server.protocol.__path__.insert(0,str(W/'candidate/els_server/protocol'))
from els_server.protocol import mentor_messages as wire
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
import runtime_queries as q
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RDX,UC_X86_REG_RSP,UC_X86_REG_RIP
report=dict(ok=False,image_sha256=IMAGE_SHA,native_consumer='12401B0',live_process_access=False,natural_GUI=False,cases=[])
try:
    md=q.capstone.Cs(q.capstone.CS_ARCH_X86,q.capstone.CS_MODE_64)
    entry=0x12401b0;begin,end,_=q.owner(entry)
    rows=list(md.disasm_lite(q.b[begin:end],q.base+begin))
    finish=next(pc+size-q.base for pc,size,op,args in rows if op=='call'and args=='0x143b6d160')
    reads={0x3b6d640:'name',0x3b6d340:'i32',0x3b6d2d0:'channel'}
    sites={pc+size for pc,size,op,args in rows if op=='call'and args.startswith('0x')
           and int(args,16)-q.base in reads and pc-q.base<finish}
    assert len(sites)==4
    r=Replay();destinations=[]
    def capture(uc,address,size,user):
        caller=struct.unpack('<Q',r.read(uc.reg_read(UC_X86_REG_RSP),8))[0]
        if caller in sites:destinations.append((reads[address-r.base],uc.reg_read(UC_X86_REG_RDX)))
    for address in reads:r.uc.hook_add(UC_HOOK_CODE,capture,begin=r.base+address,end=r.base+address)
    r.uc.hook_add(UC_HOOK_CODE,lambda uc,a,n,u:uc.reg_write(UC_X86_REG_RIP,r.stop),
                  begin=r.base+finish,end=r.base+finish)
    def text(address):
        length,capacity=struct.unpack('<QQ',r.read(address+16,16));assert length<64
        data=address if capacity<=7 else struct.unpack('<Q',r.read(address,8))[0]
        return r.read(data,length*2).decode('utf-16le')
    for name,level,career,channel in [('找师傅A',1,1,1),('OwnStudent',35,106,1),('🙂徒弟',98,205,65535)]:
        row=dict(name=name,level=level,unit_class=career)
        raw=wire.search_notice(row,channel).payload
        _,buffer=stream(r,raw);manager=r.alloc(0x200);destinations.clear()
        r.write(r.stack+0x20,struct.pack('<Q',buffer))
        r.call(entry,manager,0,0,0x716)
        assert [kind for kind,address in destinations]==['name','i32','i32','channel']
        addresses=[address for kind,address in destinations]
        assert [text(addresses[0]),*struct.unpack('<i',r.read(addresses[1],4)),
                *struct.unpack('<i',r.read(addresses[2],4)),*struct.unpack('<H',r.read(addresses[3],2))]==[name,level,career,channel]
        assert struct.unpack('<I',r.read(buffer+32,4))[0]==len(raw)
        report['cases'].append(dict(bytes=len(raw),name=name,level=level,unit_class=career,channel=channel,all_original_fields_match=True))
    report.update(ok=True,original_prefix_sha256=hashlib.sha256(q.b[entry:finish]).hexdigest(),
        original_consumer_stop_rva=hex(finish),stopped_before_UI_globals=True,
        source_sha256=hashlib.sha256(Path(wire.__file__).read_bytes()).hexdigest())
except BaseException:
    report['error']=traceback.format_exc()
    if 'r'in locals():report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=W/('search-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));raise SystemExit(not report['ok'])
