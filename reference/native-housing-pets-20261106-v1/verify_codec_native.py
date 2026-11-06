"""Current original placement readers and serializer primitives in private memory."""
from pathlib import Path
import ast,hashlib,importlib.util,json,os,struct,sys,time,traceback
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
 production_database_access=False,business_connection=False,checks=[])
try:
 r=Replay()
 def head():
  p=r.alloc(0x120);r.write(p,struct.pack('<QQQ',p,p,p));r.write(p+0x18,b'\1\1');return p
 def tree(address):
  p=head();r.write(address,struct.pack('<QQ',p,0));return p
 def read_tree(address,wanted):
  h,count=struct.unpack('<QQ',r.read(address,16));assert count==len(wanted)
  seen=[]
  def visit(p):
   if p==h:return
   assert len(seen)<=256
   left,_,right=struct.unpack('<QQQ',r.read(p,24));visit(left)
   slot,tag,date=struct.unpack('<BBQ',r.read(p+0x1a,10))
   uid,unit=struct.unpack('<Qi',r.read(p+0x24,12));step=r.read(p+0x50,1)[0]
   seen.append((slot,tag,date,uid,unit,step));visit(right)
  visit(int.from_bytes(r.read(h+8,8),'little'))
  assert seen==[(a,b,c,p['uid'],p['unit'],p['step'])for a,b,c,p in wanted],(seen,wanted)
  r.call(0xc7d680,address,address,int.from_bytes(r.read(h+8,8),'little'))
  return seen
 choices=0
 for slot in range(256):
  for uid in(0,2**64-1):
   s,b=stream(r,bytes(32));first=int.from_bytes(r.read(b+8,8),'little');r.write(b+16,struct.pack('<Q',first))
   assert r.call(0x3b6da90,s,slot)&255==1
   assert r.call(0x3b6dda0,s,uid)&255==1
   start,end=struct.unpack('<QQ',r.read(b+8,16));raw=r.read(start,end-start)
   assert wire.placement_request(raw)==(slot,uid);choices+=1
 report['checks'].append(dict(original_A38_primitives=['3B6DA90','3B6DDA0'],
  original_factory='3336220',all_byte_slots=True,UID_u64_boundaries=True,cases=choices))
 fixtures=[(1,0,0,dict(uid=9001,unit=1,name='甲',step=0)),
  (2,255,2**64-1,dict(uid=9002,unit=30000,name='乙🙂',step=3)),
  (3,1,1793942000,dict(uid=9003,unit=103,name='C',step=2)),
  (4,2,2**63,dict(uid=9004,unit=10041,name='D',step=1))]
 for rows in([],fixtures[:1],fixtures):
  raw=wire.placements(rows)
  s,b=stream(r,raw);v=r.alloc(16);tree(v);r.call(0x2be1f10,s,v)
  assert int.from_bytes(r.read(b+32,4),'little')==len(raw);read_tree(v,rows)
  # The A37 wrapper constructs its own native stream over the same buffer.
  s,b=stream(r,raw);v=r.alloc(16);tree(v);r.call(0xc4f840,b,v)
  assert int.from_bytes(r.read(b+32,4),'little')==len(raw);read_tree(v,rows)
  for result in(-2147483648,0,2147483647):
   ack=wire.placement_ack(result,rows);s,b=stream(r,ack.payload)
   v=r.alloc(20);tree(v+4);r.call(0x332f920,b,v)
   assert struct.unpack('<i',r.read(v,4))[0]==result
   assert int.from_bytes(r.read(b+32,4),'little')==len(ack.payload);read_tree(v+4,rows)
 report['checks'].append(dict(original_readers=['2BE1F10','C4F840','332F920'],
  record_counts=[0,1,4],exact_slot_byte_Q_UID_unit_step=True,result_i32_boundaries=True,
  time_and_auxiliary_byte_are_layout_fixtures=True))
 baseline=H.parent/'transport-routing-variants-v1/full-source-v1/els_server/protocol/housing_messages.py'
 spec=importlib.util.spec_from_file_location('qualified_housing_baseline',baseline);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 value=room_dto(dict(uid=7001,name='Owner',level=99,unit_type=0))
 assert entry.entry_snapshot(value)==old.entry_snapshot(value)
 value['1b4']=fixtures
 assert wire.placements(fixtures)in entry.entry_snapshot(value)
 report['checks'].append(dict(empty_924_byte_parity=True,nonempty_924_1B4_supported=True,
  full_924_native_reader_not_claimed=True))
 for n in range(10):
  if n==9:continue
  try:wire.placement_request(bytes(n))
  except ValueError:pass
  else:raise AssertionError(('bad request length',n))
 for rows in([fixtures[0],fixtures[0]],list(reversed(fixtures)),[(256,0,0,fixtures[0][3])],[(1,256,0,fixtures[0][3])],[(1,0,-1,fixtures[0][3])]):
  try:wire.placements(rows)
  except ValueError:pass
  else:raise AssertionError('noncanonical placement accepted')
 report['checks'].append(dict(malformed_lengths_duplicate_and_out_of_order_slots_rejected=True,
  scalar_boundaries_rejected=True))
 report.update(ok=True,source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
  for p in(H/'candidate/els_server/protocol').glob('*.py')})
except BaseException:
 report['error']=traceback.format_exc()
 if 'r'in locals():
  from unicorn.x86_const import UC_X86_REG_RIP
  report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=H/('codec-native-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False))
raise SystemExit(not report['ok'])
