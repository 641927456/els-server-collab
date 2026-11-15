"""Original71A consumer stores the seven/thirty-day expiry in native CUser."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
B=W.parent/'duel-wire-v2/full-source'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
from els_server.protocol.resonance_period_messages import notice
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
import runtime_queries as q
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RIP
report=dict(ok=False,image_sha256=IMAGE_SHA,original_consumer='D36480/71A',
    live_process_access=False,natural_GUI=False,cases=[])
try:
    md=q.capstone.Cs(q.capstone.CS_ARCH_X86,q.capstone.CS_MODE_64)
    begin,end,_=q.owner(0xd36480)
    rows=list(md.disasm_lite(q.b[begin:end],q.base+begin))
    finish=next(pc-q.base for pc,size,op,args in rows if op=='call'and args=='0x140d36980')
    r=Replay();manager=r.alloc(0x600);scene=r.alloc(0x200);user=r.alloc(0x3000)
    r.write(r.base+0x4817e70,struct.pack('<Q',manager));r.write(manager+200,struct.pack('<Q',scene));r.write(scene+0xa0,struct.pack('<Q',user))
    r.uc.hook_add(UC_HOOK_CODE,lambda uc,a,n,u:uc.reg_write(UC_X86_REG_RIP,r.stop),begin=r.base+finish,end=r.base+finish)
    for stat,points,expires,page in((1,5,1793910000+604800,1),(12,5,1793910000+2592000,4),(0,0,0,1)):
        raw=notice(SimpleNamespace(field21=stat,field25=points,field29=expires,selected_page=page)).payload
        _,buffer=stream(r,raw);panel=r.alloc(0x300);r.write(r.stack+0x20,struct.pack('<Q',buffer))
        r.call(0xd36480,panel,0,0,0x71a)
        assert struct.unpack('<iiQB',r.read(user+0x28bd,17))==(stat,points,expires,page)
        assert struct.unpack('<H',r.read(panel+0xea,2))[0]==page
        assert struct.unpack('<I',r.read(buffer+32,4))[0]==len(raw)==17
        report['cases'].append(dict(stat=stat,points=points,expires_at=expires,page=page,original_CUser_fields_match=True))
    report.update(ok=True,original_prefix_sha256=hashlib.sha256(q.b[0xd36480:finish]).hexdigest(),
        stop_before_native_UI_refresh=hex(finish),wire_readers_unmodified=True)
except BaseException:
    report['error']=traceback.format_exc()
    if 'r'in locals():report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=W/('blessing-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out))));raise SystemExit(not report['ok'])
