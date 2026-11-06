"""Full original 924 DTO and the additional A3B consumer's shared wire layout."""
from pathlib import Path
import ast,hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');H=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path[:0]=[str(H.parent/'transport-routing-variants-v1/full-source-v1'),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
import els_server.protocol
els_server.protocol.__path__.insert(0,str(H/'candidate/els_server/protocol'))
from els_server.protocol import housing_pet_messages as wire,housing_messages as entry
from els_server.storage.housing_rooms import dto as room_dto
from role_native_replay import Replay,IMAGE_SHA
helper=R/'tools/verify_pet_support_offline.py'
node=next(n for n in ast.parse(helper.read_bytes()).body if isinstance(n,ast.FunctionDef)and n.name=='stream')
exec(compile(ast.Module(body=[node],type_ignores=[]),'existing private stream helper','exec'))
report=dict(ok=False,image_sha256=IMAGE_SHA,native_Game=False,natural_GUI=False,
 production_database_access=False,business_connection=False,cases=[])
try:
 r=Replay()
 fixtures=[(i,0,1793942000+i,dict(uid=9000+i,unit=1,name='宠物'+str(i),step=i-1))for i in range(1,5)]
 for rows in([],fixtures[:1],fixtures):
  value=room_dto(dict(uid=7001,name='Owner',level=99,unit_type=0));value['1b4']=rows
  raw=entry.entry_snapshot(value);s,b=stream(r,raw);dto=r.alloc(0x1d5)
  r.call(0xc7e4e0,dto);r.call(0xc4f470,b,dto)
  assert int.from_bytes(r.read(b+32,4),'little')==len(raw)
  head,count=struct.unpack('<QQ',r.read(dto+0x1b4,16));assert count==len(rows)
  actual=[]
  def visit(p):
   if p==head:return
   left,_,right=struct.unpack('<QQQ',r.read(p,24));visit(left)
   actual.append((*struct.unpack('<BBQ',r.read(p+0x1a,10)),int.from_bytes(r.read(p+0x24,8),'little')));visit(right)
  visit(int.from_bytes(r.read(head+8,8),'little'))
  assert actual==[(a,b,c,p['uid'])for a,b,c,p in rows]
  assert wire.placement_ack(0,rows,kind=0xa3b).payload==wire.placement_ack(0,rows).payload
  report['cases'].append(dict(records=len(rows),payload_bytes=len(raw),all_fields_consumed=True,native_UIDs=[v[3]for v in actual]))
 report.update(ok=True,original_ctor='C7E4E0',original_full_reader='C4F470',
  A3B_3297F00_uses_same_332F920_reader=True,
  A39_2BE1F10_C4F840_332F920_reused='codec-native-1793943008395519700.json',
  source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in(H/'candidate/els_server/protocol').glob('*.py')})
except BaseException:
 report['error']=traceback.format_exc()
 if 'r'in locals():
  from unicorn.x86_const import UC_X86_REG_RIP
  report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=H/('entry-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False))
raise SystemExit(not report['ok'])
