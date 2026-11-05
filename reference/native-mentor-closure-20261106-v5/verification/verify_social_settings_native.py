"""Exhaust all ten original preference bits and consume full2F with original code."""
from pathlib import Path
import hashlib,json,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent;B=W/'full-source-v2'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
from els_server.protocol.social_settings_messages import DEFAULT,validate
from els_server.protocol.local_messages import optional_player_initializations
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
report=dict(ok=False,image_sha256=IMAGE_SHA,live_process_access=False,natural_GUI=False,cases=[])
try:
    r=Replay()
    for mask in range(1024):
        raw=validate(bytes((mask>>i)&1 for i in range(10)))
        s,b=stream(r,raw);dto=r.alloc(10)
        assert r.call(0xdb3070,s,dto)&255==1
        assert r.read(dto,10)==raw and int.from_bytes(r.read(b+32,4),'little')==10
    report['cases'].append('All1024 ten-boolean combinations consumed byte-for-byte by untouched DB3070')
    for settings,health,selector in ((DEFAULT,100,0),(bytes(10),2147483647,1),(bytes([1])*10,375,0)):
        raw=next(e for e in optional_player_initializations(True,1001,health_max=health,luciel_active=selector,social_settings=settings)if e.kind==0x2f).payload
        s,b=stream(r,raw);dto=r.alloc(0x164);r.call(0x13f7550,dto)
        assert r.call(0xda37c0,s,dto)&255==1
        assert int.from_bytes(r.read(b+32,4),'little')==len(raw)
        assert r.read(dto+0x1c,10)==settings
        report['cases'].append(dict(original_full2F_reader=True,preferences=settings.hex(),health_max=health,luciel_active=selector,consumed=len(raw)))
    report['ok']=True
except BaseException:report['error']=traceback.format_exc()
report['binding_sha256']=hashlib.sha256((W/'candidate-source-binding-v2.json').read_bytes()).hexdigest()
out=W/('social-settings-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out))));raise SystemExit(not report['ok'])
