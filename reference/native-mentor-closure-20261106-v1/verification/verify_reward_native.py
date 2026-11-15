"""Original native item body reader for the finite mentor reward definitions."""
from pathlib import Path
import hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
B=R/'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
from els_server.domain.inventory_items import _encode_item_body
from role_native_replay import Replay,IMAGE_SHA
from verify_pet_support_offline import stream
from unicorn.x86_const import UC_X86_REG_RIP
data_path=W/'candidate/els_server/data/mentor_quests.json';data=json.loads(data_path.read_bytes())
report=dict(ok=False,image_sha256=IMAGE_SHA,original_reader='D9A550',original_constructor='7DD4F0',
    live_process_access=False,production_database_access=False,natural_GUI=False,cases=[])
try:
    r=Replay()
    for row in data['reward_definitions']:
        if row['previously_registered']:continue
        for count in ((1,)if row['max_stack']==1 else(1,row['max_stack'])):
            item=dict(uid=123456,template=row['template'],metadata=row['metadata'],
                      group=row['group'],slot=0,count=count)
            raw=_encode_item_body(item);incoming,buffer=stream(r,raw);dto=r.alloc(0x400)
            r.call(0x7dd4f0,dto)
            assert r.call(0xd9a550,incoming,dto)&255==1
            assert struct.unpack('<I',r.read(buffer+32,4))[0]==len(raw)==304
            assert struct.unpack('<IBi',r.read(dto,9))==(row['template'],row['metadata'],count)
            report['cases'].append(dict(template=row['template'],metadata=row['metadata'],count=count,
                native_bytes=304,all_original_identity_fields_match=True))
    report.update(ok=True,data_sha256=hashlib.sha256(data_path.read_bytes()).hexdigest(),
        scope='Body parser only; inventory acquisition/owned-reader validation is qualified separately')
except BaseException:
    report['error']=traceback.format_exc()
    if 'r'in locals():report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=W/('rewards-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out))));raise SystemExit(not report['ok'])
