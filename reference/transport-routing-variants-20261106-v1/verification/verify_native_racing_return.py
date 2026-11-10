"""Pinned racing reason plus original complete-statistic wire writer."""
from pathlib import Path
import ast,hashlib,json,os,struct,sys,time,traceback
W=Path(__file__).resolve().parent;R=Path('G:/els')
sys.path[:0]=[str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
from role_native_replay import Replay,IMAGE_SHA
helper=R/'tools/verify_pet_support_offline.py'
node=next(n for n in ast.parse(helper.read_text('utf8')).body if isinstance(n,ast.FunctionDef)and n.name=='stream')
exec(compile(ast.Module(body=[node],type_ignores=[]),str(helper)+' stream only','exec'))
import runtime_queries as q

report=dict(ok=False,native_Game=False,natural_GUI=False,layout_fixture=True,image_sha256=IMAGE_SHA,
            reason_source='2B228D0 calls virtual270 with0x72;42AA040+270 points to1AB2B10;1AB2B10 forwards its reason unchanged to original67 DTO')
try:
    # Inspect exact native instructions, not our own decompiler names.
    md=q.capstone.Cs(q.capstone.CS_ARCH_X86,q.capstone.CS_MODE_64)
    b,e,_=q.owner(0x2b22b3f)
    assert q.primary(q.owner(0x2b22b3f))[0]==0x2b228d0
    assert any(op=='mov'and args=='edx, 0x72'for pc,n,op,args in md.disasm_lite(q.b[b:e],q.base+b))
    assert struct.unpack_from('<Q',q.b,0x42aa040+0x270)[0]==q.base+0x1ab2b10
    r=Replay();stat=r.alloc(1024);r.call(0xc79fb0,stat)
    writer,buffer=stream(r,bytes(4096));start=int.from_bytes(r.read(buffer+8,8),'little')
    r.write(buffer+16,struct.pack('<Q',start))
    assert r.call(0x3b6dbd0,writer,0x72)&255==1
    assert r.call(0xda2f50,writer,stat)&255==1
    assert r.call(0x3b6dbd0,writer,0)&255==1
    first,last=struct.unpack('<QQ',r.read(buffer+8,16));raw=r.read(first,last-first)
    assert len(raw)==190 and raw[:4]==struct.pack('>i',0x72)
    report.update(ok=True,wire_hex=raw.hex(),bytes=len(raw),statistic_ctor='C79FB0',complete_statistic_writer='DA2F50',
        original_writers_unmodified=True,live_process_access=False)
except BaseException:report['error']=traceback.format_exc()
p=W/('native-racing-return-'+str(time.time_ns())+'.json')
p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps({k:v for k,v in report.items()if k!='wire_hex'}|dict(evidence=str(p)),ensure_ascii=False))
raise SystemExit(not report['ok'])
