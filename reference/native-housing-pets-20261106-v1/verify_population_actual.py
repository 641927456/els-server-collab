"""Original full parser of actual92F packets, including current custom state."""
from pathlib import Path
import ast,hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');H=Path(__file__).resolve().parent
sys.dont_write_bytecode=True;sys.path[:0]=[str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
from role_native_replay import Replay,IMAGE_SHA
helper=R/'tools/verify_pet_support_offline.py'
node=next(n for n in ast.parse(helper.read_bytes()).body if isinstance(n,ast.FunctionDef)and n.name=='stream')
exec(compile(ast.Module(body=[node],type_ignores=[]),'existing stream helper','exec'))
source=H/'population-TLS-1793945548789159100.json';proof=json.loads(source.read_bytes());assert proof['ok']
report=dict(ok=False,image_sha256=IMAGE_SHA,TLS_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),native_Game=False,natural_GUI=False,cases=[])
try:
 r=Replay()
 def head(size):
  p=r.alloc(size);r.write(p,struct.pack('<QQQ',p,p,p));r.write(p+0x18,b'\1\1');return p
 for packet in proof['packets']:
  if packet['kind']!=0x92f:continue
  raw=bytes.fromhex(packet['payload_hex']);s,b=stream(r,raw);dto=r.alloc(0x4c)
  for offset,size in((0x1c,0x40),(0x2c,0x38),(0x3c,0x30)):r.write(dto+offset,struct.pack('<QQ',head(size),0))
  r.call(0x2b4f560,s,dto)
  assert int.from_bytes(r.read(b+32,4),'little')==len(raw)
  result=struct.unpack('<i',r.read(dto,4))[0];assert result==struct.unpack_from('>i',raw)[0]
  first,last,capacity=struct.unpack('<QQQ',r.read(dto+4,24));count=(last-first)//0x13d
  if result==0:
   assert count==1 and int.from_bytes(r.read(first+8,8),'little')==proof['owner']
   assert struct.unpack('<H',r.read(first+0x67,2))[0]==1 and r.read(first+0x6f,1)[0]==99
   length,cap=struct.unpack('<QQ',r.read(first+0x41,16));p=first+0x31 if cap<=7 else int.from_bytes(r.read(first+0x31,8),'little')
   assert r.read(p,length*2).decode('utf-16le')=='HomeOwner'
  else:assert count==0
  report['cases'].append(dict(result=result,records=count,consumed=len(raw),payload_sha256=hashlib.sha256(raw).hexdigest()))
 assert len(report['cases'])==3
 report.update(ok=True,reader='2B4F560 -> DA4EB0',actual_SQL_name_class_level_preserved=True,
  native_self_actor_factory_not_executed=True)
except BaseException:report['error']=traceback.format_exc()
out=H/('population-actual-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False))
raise SystemExit(not report['ok'])
