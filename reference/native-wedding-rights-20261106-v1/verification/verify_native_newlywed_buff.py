"""Original marriage buff branch with explicit actor/roster test doubles."""
from pathlib import Path
import hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path[:0]=[str(W/'title-test-source-v1'),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_RIP
from els_server.game_data import client_data

report=dict(ok=False,native_Game=False,natural_GUI=False,image_sha256=IMAGE_SHA,
 original_function='194BF20',actor_virtuals_and_roster_lookup_are_explicit_fixtures=True,cases=[])
try:
 data=client_data();enums=data.resource('Enum.lua')
 assert enums['BUFF_FACTOR_ID']['BFI_NEW_WEDDING_DUNGEON']==1617
 assert enums['BUFF_TEMPLET_ID']['BTI_NEW_WEDDING_DUNGEON']==1508
 resource=R/'analysis/current-pve-exp-20261020-v1/expanded-20261104-v1/matched-tables/data036.kom/BattleFieldBuffFactor.lua.tables.json'
 table=json.loads(resource.read_bytes());calls=table if isinstance(table,list)else table['__symbolic_calls__']
 native=next(c['arguments'][1]for c in calls if isinstance(c['arguments'][1],dict)and c['arguments'][1].get('BUFF_FACTOR_ID')=={'global':'BUFF_FACTOR_ID.BFI_NEW_WEDDING_DUNGEON'})
 behavior=native['BUFF_FACTOR']['BEHAVIOR']
 for key in('BBT_CHANGE_PHYSIC_ATTACK','BBT_CHANGE_MAGIC_ATTACK'):
  assert set(v for v in behavior[key]['PERCENT'].values()if v is not None)=={1.05}
 r=Replay();callbacks=[];now=1793950000;present=True;result=[]
 def hook(value):
  address=r.alloc(16);r.write(address,b'\xc3')
  def invoke(uc,a,n,u):r.finish_shim(value()if callable(value)else value)
  callbacks.append(invoke);r.uc.hook_add(UC_HOOK_CODE,invoke,begin=address,end=address);return address
 def intercept(rva,value):
  def invoke(uc,a,n,u):r.finish_shim(value()if callable(value)else value)
  callbacks.append(invoke);r.uc.hook_add(UC_HOOK_CODE,invoke,begin=r.base+rva,end=r.base+rva)
 def qword(p,v):r.write(p,struct.pack('<Q',v))
 engine=r.alloc(0x700);manager=r.alloc(0x30);relation=r.alloc(0x100)
 qword(r.base+0x4817e70,engine);qword(engine+0x618,manager);qword(manager+8,relation)
 r.write(relation,struct.pack('<I',2));qword(relation+8,1002);qword(relation+0x80,now-1)
 actor=r.alloc(0x2000);actor_vtable=r.alloc(0x700);qword(actor,actor_vtable)
 state=r.alloc(0x20);state_vtable=r.alloc(0x300);qword(state,state_vtable)
 qword(state_vtable+0x230,hook(2))
 def lookup():
  assert r.uc.reg_read(UC_X86_REG_RDX)==1002
  return actor if present else 0
 qword(state_vtable+0x150,hook(lookup));qword(actor_vtable+0x460,hook(1))
 def apply():
  result.append([r.uc.reg_read(reg)for reg in(UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9)])
  return 0
 qword(actor_vtable+0x5f8,hook(apply))
 entries=r.alloc(0x20);weak_vector=r.alloc(0x20)
 qword(weak_vector,entries);qword(weak_vector+8,entries+0x20)
 r.write(entries+0xc,struct.pack('<I',1));r.write(entries+0x10,struct.pack('<I',1));qword(entries,state)
 r.write(r.base+0x478cb88,struct.pack('<ii',0,1))
 intercept(0x1528f0,weak_vector);intercept(0x15a100,state)
 qword(r.base+0x3ea9610,hook(0));qword(r.base+0x3ea9fb0,hook(lambda:now))
 for name,kind,peer,elapsed,expected in(
  ('married together before30days',2,True,2591999,[[1617,0,1]]),
  ('married partner absent',2,False,1,[]),
  ('exact30day expiry',2,True,2592000,[]),
  ('ordinary couple',1,True,1,[]),('solo after divorce',0,True,1,[])):
  result.clear();present=peer;r.write(relation,struct.pack('<I',kind));qword(relation+0x80,now-elapsed)
  r.call(0x194bf20,actor)
  assert result==expected,(name,result)
  report['cases'].append(dict(name=name,original_added_factor=list(result)))
 report.update(ok=True,factor_id=1617,template_id=1508,physical_multiplier=1.05,magical_multiplier=1.05,
  new_buff_implementation_needed=False,source_table_sha256=hashlib.sha256(resource.read_bytes()).hexdigest())
except BaseException:
 report['error']=traceback.format_exc()
 if 'r'in locals():report['native_pc']=hex(r.uc.reg_read(UC_X86_REG_RIP)-r.base)
out=W/('native-newlywed-buff-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));raise SystemExit(not report['ok'])
