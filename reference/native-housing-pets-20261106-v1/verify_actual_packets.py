"""Original readers consume the actual authenticated TLS placement/entry output."""
from pathlib import Path
import ast,hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');H=Path(__file__).resolve().parent
sys.dont_write_bytecode=True;sys.path[:0]=[str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
from role_native_replay import Replay,IMAGE_SHA
helper=R/'tools/verify_pet_support_offline.py'
node=next(n for n in ast.parse(helper.read_bytes()).body if isinstance(n,ast.FunctionDef)and n.name=='stream')
exec(compile(ast.Module(body=[node],type_ignores=[]),'existing stream helper','exec'))
source=H/'writer-TLS-1793944369243651700.json';proof=json.loads(source.read_bytes());assert proof['ok']
report=dict(ok=False,image_sha256=IMAGE_SHA,TLS_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
 native_Game=False,natural_GUI=False,actual_original_readers=True,cases=[])
try:
 r=Replay()
 for packet in proof['packets']:
  kind=packet['kind']
  if kind not in(0x924,0xa39,0xa3b):continue
  raw=bytes.fromhex(packet['payload_hex']);s,b=stream(r,raw)
  if kind==0x924:
   dto=r.alloc(0x1d5);r.call(0xc7e4e0,dto);r.call(0xc4f470,b,dto);offset=0x1b4
  else:
   dto=r.alloc(20);head=r.alloc(0x120);r.write(head,struct.pack('<QQQ',head,head,head));r.write(head+0x18,b'\1\1')
   r.write(dto+4,struct.pack('<QQ',head,0));r.call(0x332f920,b,dto);offset=4
  assert int.from_bytes(r.read(b+32,4),'little')==len(raw)
  result=struct.unpack('<i',r.read(dto,4))[0];assert result==struct.unpack_from('>i',raw)[0]
  head,count=struct.unpack('<QQ',r.read(dto+offset,16));seen=[]
  def visit(p):
   if p==head:return
   assert len(seen)<5
   left,_,right=struct.unpack('<QQQ',r.read(p,24));visit(left)
   seen.append(dict(slot=r.read(p+0x1a,1)[0],started_at=int.from_bytes(r.read(p+0x1c,8),'little'),
    pet=int.from_bytes(r.read(p+0x24,8),'little'),unit=struct.unpack('<i',r.read(p+0x2c,4))[0],step=r.read(p+0x50,1)[0]))
   visit(right)
  visit(int.from_bytes(r.read(head+8,8),'little'));assert len(seen)==count
  report['cases'].append(dict(kind=kind,result=result,payload_sha256=hashlib.sha256(raw).hexdigest(),
   consumed=len(raw),records=seen))
 assert {len(c['records'])for c in report['cases']}=={0,1,2,3,4}
 report.update(ok=True,full_924_and_A39_A3B_shared_reader=True,
  original_state_pending_gates_and_3D_scene_not_claimed=True)
except BaseException:report['error']=traceback.format_exc()
out=H/('actual-packets-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps({k:v for k,v in report.items()if k!='cases'}|dict(cases=len(report['cases']),evidence=str(out)),ensure_ascii=False))
raise SystemExit(not report['ok'])
