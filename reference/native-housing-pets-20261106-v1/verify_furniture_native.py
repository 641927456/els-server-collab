"""Full924 nonempty furniture reader and the original runtime layout copy."""
from pathlib import Path
import ast,hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');H=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path[:0]=[str(H.parent/'transport-routing-variants-v1/full-source-v1'),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
import els_server.protocol
els_server.protocol.__path__.insert(0,str(H/'candidate/els_server/protocol'))
from els_server.protocol.housing_messages import entry_snapshot
from els_server.storage.housing_rooms import dto as room_dto
from role_native_replay import Replay,IMAGE_SHA
helper=R/'tools/verify_pet_support_offline.py'
node=next(n for n in ast.parse(helper.read_bytes()).body if isinstance(n,ast.FunctionDef)and n.name=='stream')
exec(compile(ast.Module(body=[node],type_ignores=[]),'existing stream helper','exec'))
report=dict(ok=False,image_sha256=IMAGE_SHA,native_Game=False,natural_GUI=False,cases=[])
try:
 r=Replay()
 def modern(layout):
  head,count=struct.unpack('<QQ',r.read(layout+16,16));assert count==1
  node=int.from_bytes(r.read(head+8,8),'little')
  key=int.from_bytes(r.read(node+0x20,8),'little')
  uid,template,position,x,y,z,direction=struct.unpack('<Qiifffi',r.read(node+0x28,32))
  return key,uid,template,position,(x,y,z),direction
 for template in (570234,570286,580119):
  uid=1001012;xyz=(0.,0.,0.);rows=[(uid,(uid,template,2,xyz,0))]
  value=room_dto(dict(uid=1001,name='OwnHome',level=99,unit_type=1));value['0f7']=[(0,([],rows,[],0,0))]
  raw=entry_snapshot(value);s,b=stream(r,raw);dto=r.alloc(0x1d5)
  r.call(0xc7e4e0,dto);r.call(0xc4f470,b,dto)
  assert int.from_bytes(r.read(b+32,4),'little')==len(raw)
  head,count=struct.unpack('<QQ',r.read(dto+0xf7,16));assert count==1
  node=int.from_bytes(r.read(head+8,8),'little')
  assert int.from_bytes(r.read(node+0x1c,4),'little')==0
  # 2C275A0/2BE2300: int key at1C, native layout value at20.
  saved=node+0x20;actual=modern(saved)
  assert actual==(uid,uid,template,2,xyz,0),actual
  copied=r.alloc(0x38);r.call(0xc78e30,copied,saved)
  assert modern(copied)==actual
  report['cases'].append(dict(template=template,uid=uid,original_full924=True,
   full_payload_consumed=len(raw),original_C78E30_runtime_copy=True,
   actual_template=actual[2],actual_position=actual[3],actual_xyz=actual[4]))
 report.update(ok=True,reader='C7E4E0/C4F470 ->2BE1CB0/2BE2300; C78E30/C78BF0 runtime copy',
  source_sha256=hashlib.sha256((H/'candidate/els_server/protocol/housing_messages.py').read_bytes()).hexdigest(),
  model_or_scene_creation_not_executed=True)
except BaseException:
 report['error']=traceback.format_exc()
 if 'r'in locals():
  from unicorn.x86_const import UC_X86_REG_RIP
  report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=H/('furniture-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False))
raise SystemExit(not report['ok'])
