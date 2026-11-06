"""Native furniture classification, original merchant source and layout rules."""
from pathlib import Path
import hashlib,json,os,struct,sys,time,traceback
R=Path('G:/els');H=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path[:0]=[str(H.parent/'transport-routing-variants-v1/full-source-v1'),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
import els_server.domain,els_server.protocol
els_server.domain.__path__.insert(0,str(H/'candidate/els_server/domain'))
els_server.protocol.__path__.insert(0,str(H/'candidate/els_server/protocol'))
from els_server.domain import housing_pet_rules as rules,furniture_rules as furniture
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
from els_server.domain.acquisition_policy import can_acquire
from els_server.domain.npc_trade import offer,stock
from els_server.game_data import client_data
from role_native_replay import Replay,IMAGE_SHA
report=dict(ok=False,image_sha256=IMAGE_SHA,native_Game=False,natural_GUI=False,
 production_database_access=False,rows=[])
try:
 r=Replay();c=client_data();definitions=furniture.definitions()
 for template in sorted(rules.TEMPLATES):
  item=c.item(template);p=r.alloc(232);r.write(p,item['record']);group=r.call(0x19803a0,0,p)&0xffffffff
  assert group==25 and VERIFIED_TEMPLATES[template]==0 and TEMPLATE_BAG_GROUPS[template]==25 and TEMPLATE_MAX_STACKS[template]==1
  assert can_acquire(template)is(template==570234)
  owned=dict(uid=7000+template,template=template,metadata=0,group=25,count=1,sealed=False)
  layout=([(owned['uid'],(2,owned['uid'],template,1,2,0))],[],[],0,-1)
  assert furniture.validate_layout(layout,[owned],mutating=True,now=1793942000)==layout
  mat=rules.mat(layout);capacity,period=rules.MATS[template]
  assert mat==dict(uid=owned['uid'],template=template,capacity=capacity,period=period)
  try:furniture.validate_layout(layout,[dict(owned,uid=owned['uid']+1)],mutating=True,now=1793942000)
  except ValueError:pass
  else:raise AssertionError('Foreign furniture UID accepted')
  floating=([],[(owned['uid'],(owned['uid'],template,2,(1.,2.,0.),0))],[],0,-1)
  try:furniture.validate_layout(floating,[owned],mutating=True,now=1793942000)
  except ValueError as e:assert str(e)=='Housing pet mats require native grid placement'
  else:raise AssertionError('Nonprojecting free-position pet mat accepted')
  report['rows'].append(dict(template=template,native_group=group,metadata=item['metadata'],
   record_sha256=hashlib.sha256(item['record']).hexdigest(),capacity=capacity,period=period,
   normal_new_source=template==570234,existing_owned_layout=True,foreign_UID_rejected=True,free_position_mat_rejected=True))
 assert offer(20000,10018,570234)==30000000
 assert all(t not in values for t in rules.OWNED_ONLY for values in stock().values())
 a,b=570234,570286
 items=[dict(uid=t+7000,template=t,metadata=0,group=25,count=1,sealed=False)for t in(a,b)]
 layout=([(i['uid'],(2,i['uid'],i['template'],0,0,0))for i in items],[],[],0,-1)
 try:furniture.validate_layout(layout,items,mutating=True,now=1793942000)
 except ValueError as e:assert str(e)=='Housing permits one pet mat'
 else:raise AssertionError('Two pet mats accepted')
 assert [(v['template'],v['quantity'])for v in furniture.plan()]==[(570011,1),(570012,1),(570015,2),(570016,1)]
 report.update(ok=True,original_bag_factory='19803A0',small_mat_merchant=10018,small_mat_ED=30000000,
  original_box_136039_outputs_unchanged=True,one_mat_limit=True,all_five_large_mats_owned_only=True,
  source_sha256={str(p.relative_to(H/'candidate')):hashlib.sha256(p.read_bytes()).hexdigest()
   for p in(H/'candidate').rglob('*.py')})
except BaseException:report['error']=traceback.format_exc()
out=H/('mat-admission-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False))
raise SystemExit(not report['ok'])
