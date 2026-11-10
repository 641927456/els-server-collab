"""Original167 serializer and168 setting assignment, no live process."""
from pathlib import Path
import hashlib,json,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent;B=W/'full-source-v2'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
from els_server.protocol.social_settings_messages import DEFAULT,reply,validate
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
from unicorn import UC_HOOK_CODE
report=dict(ok=False,image_sha256=IMAGE_SHA,live_process_access=False,natural_GUI=False,cases=[])
try:
    r=Replay()
    for mask in range(1024):
        raw=validate(bytes((mask>>i)&1 for i in range(10)));dto=r.alloc(10);r.write(dto,raw)
        data=r.alloc(16);buffer=r.alloc(48);r.write(buffer+8,struct.pack('<QQQ',data,data,data+16))
        s=r.alloc(40);r.call(0x3b6d140,s);r.call(0x3b6d1c0,s,buffer,0)
        assert r.call(0xdb2f80,s,dto)&255==1
        begin,end=struct.unpack('<QQ',r.read(buffer+8,16))
        assert end-begin==10 and r.read(begin,10)==raw
    report['cases'].append('All1024 native167 DB2F80 serialized settings exactly match validated wire bytes')
    manager=r.alloc(0x300);r.write(r.base+0x4817e80,struct.pack('<Q',manager))
    # External game-ready/error-dialog helpers do not parse or assign fields.
    for pc in (0x74ffa0,0x751120):r.uc.hook_add(UC_HOOK_CODE,lambda uc,a,n,u:r.finish_shim(1),begin=r.base+pc,end=r.base+pc)
    fields=(0x274,0x278,0x27c,0x280,0x284,0x288,0x28c,0x290)
    indexes=(0,1,2,3,6,8,7,9)
    for raw in(DEFAULT,bytes(10),bytes([1])*10):
        _,buffer=stream(r,reply(raw).payload);r.write(r.stack+0x20,struct.pack('<Q',buffer))
        r.call(0x2d53bb0,0,0,0,0x168)
        assert [struct.unpack('<i',r.read(manager+field,4))[0]for field in fields]==[raw[i]for i in indexes]
        assert int.from_bytes(r.read(buffer+32,4),'little')==14
        report['cases'].append(dict(original168_assignment=True,settings=raw.hex(),mentor_flag=raw[7],consumed=14))
    report.update(ok=True,external_game_ready_and_error_dialog_stubbed=True,wire_readers_and_writers_unmodified=True)
except BaseException:report['error']=traceback.format_exc()
report['binding_sha256']=hashlib.sha256((W/'candidate-source-binding-v2.json').read_bytes()).hexdigest()
out=W/('social-settings-native-save-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out))));raise SystemExit(not report['ok'])
