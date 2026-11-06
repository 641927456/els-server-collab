"""Original full92F reader over explicit self records and a public item fixture."""
from pathlib import Path
import ast,hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');H=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path[:0]=[str(H.parent/'transport-routing-variants-v1/full-source-v1'),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
import els_server.protocol
els_server.protocol.__path__.insert(0,str(H/'candidate/els_server/protocol'))
from els_server.protocol import housing_population_messages as wire
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.game_data import client_data
from role_native_replay import Replay,IMAGE_SHA
helper=R/'tools/verify_pet_support_offline.py'
node=next(n for n in ast.parse(helper.read_bytes()).body if isinstance(n,ast.FunctionDef)and n.name=='stream')
exec(compile(ast.Module(body=[node],type_ignores=[]),'existing stream helper','exec'))
report=dict(ok=False,image_sha256=IMAGE_SHA,native_Game=False,natural_GUI=False,production_database_access=False,cases=[])
report['source_sha256']=hashlib.sha256(Path(wire.__file__).read_bytes()).hexdigest()
try:
 r=Replay();c=client_data()
 weapon=next(t for t in VERIFIED_TEMPLATES if c.item(t)['item_type']==1)
 item=dict(uid=9009,template=weapon,metadata=VERIFIED_TEMPLATES[weapon],count=1,group=9,slot=0)
 def head(size):
  p=r.alloc(size);r.write(p,struct.pack('<QQQ',p,p,p));r.write(p+0x18,b'\1\1');return p
 def text(p):
  size,capacity=struct.unpack('<QQ',r.read(p+16,16));data=p if capacity<=7 else int.from_bytes(r.read(p,8),'little')
  return r.read(data,size*2).decode('utf-16le')
 for unit,name,level,equipment in((1,'房主',99,[]),(1,'房主🙂',99,[item]),(10,'LuCiel',50,[])):
  character=dict(uid=7001,name=name,unit_class=unit,unit_type=unit,level=level,title=0)
  xyz=(12.5,-30.0,15.0);event=wire.ready(character,xyz,equipment)
  s,b=stream(r,event.payload);dto=r.alloc(0x4c)
  for offset,size in((0x1c,0x40),(0x2c,0x38),(0x3c,0x30)):
   r.write(dto+offset,struct.pack('<QQ',head(size),0))
  r.call(0x2b4f560,s,dto)
  assert int.from_bytes(r.read(b+32,4),'little')==len(event.payload)
  first,last,capacity=struct.unpack('<QQQ',r.read(dto+4,24));assert last-first==0x13d
  assert int.from_bytes(r.read(first+8,8),'little')==7001
  assert text(first+0x31)==name
  assert struct.unpack('<fff',r.read(first+0x53,12))==xyz
  assert struct.unpack('<H',r.read(first+0x67,2))[0]==unit and r.read(first+0x6f,1)[0]==level
  assert struct.unpack('<i',r.read(first+0x128,4))[0]==-1
  start,end,capacity=struct.unpack('<QQQ',r.read(first+0x100,24));assert end-start==len(equipment)*0x37f
  if equipment:
   assert struct.unpack('<i',r.read(start+8,4))[0]==weapon
  report['cases'].append(dict(unit_fixture=unit,name=name,level=level,items=len(equipment),
   consumed=len(event.payload),self_UID=7001,full_native_reader=True))
 assert wire.request(struct.pack('>fff',*xyz))==xyz
 report.update(ok=True,reader='2B4F560 -> DA4EB0',source_sha256=hashlib.sha256(Path(wire.__file__).read_bytes()).hexdigest(),
  appearance_helper_sha256=hashlib.sha256((H.parent/'transport-routing-variants-v1/full-source-v1/els_server/protocol/social_messages.py').read_bytes()).hexdigest(),
  own_actor_factory_2448BE0_21460E0_not_executed=True)
except BaseException:
 report['error']=traceback.format_exc()
 if 'r'in locals():
  from unicorn.x86_const import UC_X86_REG_RIP
  report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=H/('population-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False))
raise SystemExit(not report['ok'])
