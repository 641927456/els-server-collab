"""Original71D record retention and720 DTO parsing, without a live game."""
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
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RAX,UC_X86_REG_RIP,UC_X86_REG_RSP

report=dict(ok=False,image_sha256=IMAGE_SHA,native_readers=['21B0CE0','C50240'],
    live_process_access=False,natural_GUI=False,cases=[])
try:
    r=Replay()
    # A disconnected UI context avoids opening a real consent dialog. Its
    # scene-type query is external to the parser; all wire readers are original.
    r.write(r.base+0x4817e70,bytes(8));r.write(r.base+0x4817e80,bytes(8))
    def scene(uc,address,size,user):
        stack=uc.reg_read(UC_X86_REG_RSP)
        target=struct.unpack('<Q',r.read(stack,8))[0]
        uc.reg_write(UC_X86_REG_RAX,0);uc.reg_write(UC_X86_REG_RSP,stack+8);uc.reg_write(UC_X86_REG_RIP,target)
    r.uc.hook_add(UC_HOOK_CODE,scene,begin=r.base+0x1a49890,end=r.base+0x1a49890)
    for identity,xyz,board,nonce in[(20001,(30.25,0.,-8.5),0,2**127+345),
                                  (1001,(-100.5,66.,0.),3,2**128-1),
                                  (1500,(0.,0.,0.),254,0)]:
        location=dict(map=identity,xyz=xyz,board=board)
        notice=wire.summon_notice(location,nonce).payload
        _,buffer=stream(r,notice);manager=r.alloc(0x200)
        r.write(r.stack+0x20,struct.pack('<Q',buffer));r.call(0x21b0ce0,manager)
        assert struct.unpack('<QQB',r.read(manager+0xf0,17))==(nonce>>64,nonce&(2**64-1),0)
        assert struct.unpack('<ifffB',r.read(manager+0x104,17))==(identity,*xyz,board)
        assert struct.unpack('<I',r.read(buffer+32,4))[0]==len(notice)
        parsed=wire.request(0x71f,b'\1'+notice);assert parsed==dict(accepted=True,echo=notice)
        raw=wire.summoned(location).payload
        _,buffer=stream(r,raw);dto=r.alloc(0x25)
        r.call(0xc50240,buffer,dto)
        assert struct.unpack('<iifffB4i',r.read(dto,0x25))==(0,identity,*xyz,board,0,0,0,0)
        assert struct.unpack('<I',r.read(buffer+32,4))[0]==len(raw)
        report['cases'].append(dict(destination=identity,XYZ=list(xyz),board=board,
            notice_bytes=len(notice),transition_bytes=len(raw),all_original_fields_match=True))
    report.update(ok=True,source_sha256=hashlib.sha256(Path(wire.__file__).read_bytes()).hexdigest(),
        original71D_full_consumer=True,external_scene_query_stubbed=True,original_wire_readers_unmodified=True)
except BaseException:
    report['error']=traceback.format_exc()
    if 'r'in locals():report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=W/('summon-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out))));raise SystemExit(not report['ok'])
