from pathlib import Path
import sys,json,struct
R=Path('G:/els');E=Path(__file__).resolve().parent;b=json.loads((E/'binding.json').read_bytes())['online'];P=Path(b['parent']);sys.path[:0]=[str(P),str(R/'tools'),str(R/'tools/pylibs')]
from els_server.game_data import client_data
from role_native_replay import Replay,IMAGE_SHA
from unicorn import UC_HOOK_CODE
r=Replay();result=[];boundary=[];class_calls=[]
root=r.alloc(0x1000);manager=r.alloc(0x1000);actor=r.alloc(0x3000);unit=r.alloc(8)
r.write(r.base+0x4817e70,struct.pack('<Q',root));r.write(root+0xc8,struct.pack('<Q',manager));r.write(manager+0xa0,struct.pack('<Q',actor));r.write(actor+0x29c0,struct.pack('<Q',unit))
def passed(*args):boundary.append('custom-registration');r.finish_shim(1)
def denied(*args):boundary.append('wrong-unit-dialog');r.finish_shim(0)
r.uc.hook_add(UC_HOOK_CODE,passed,begin=r.base+0x221a3cb,end=r.base+0x221a3cb);r.uc.hook_add(UC_HOOK_CODE,denied,begin=r.base+0x221a291,end=r.base+0x221a291);r.uc.hook_add(UC_HOOK_CODE,lambda *args:class_calls.append(1),begin=r.base+0x7eef80,end=r.base+0x7eef80)
for book in(470442,470443,480369):
 raw=client_data().item(book)['record'];assert raw[210:212]==bytes([12,201]);template=r.alloc(len(raw));r.write(template,raw)
 for actor_unit,actor_class,expected in((12,202,1),(11,201,0)):
  r.write(unit,struct.pack('<I',actor_unit));r.write(actor+0x58,struct.pack('<H',actor_class));r.write(r.stack-8+0x78,struct.pack('<Q',template));boundary.clear();class_calls.clear();answer=r.call(0x221a23c)
  assert answer==expected and not class_calls
  result.append(dict(book=book,actor_unit=actor_unit,actor_class=actor_class,native_boundary=boundary[0],wrong_template_class_not_read=True))
value=dict(ok=True,image_sha256=IMAGE_SHA,fragment='221A23C->221A3CB or221A291',original_getters=['7EF310(type)','7EF350(unit)','15D330','7EF380','7EFA50(actor unit)'],observed_not_stubbed='native branch destinations; no instruction or eligibility substitution',rows=result,offline_only=True,client_file_or_process_changes=False,natural_GUI=False)
(E/'native-source-result.json').write_text(json.dumps(value,indent=2)+'\n','utf8');print(json.dumps(dict(ok=True,cases=len(result),correct_unit_passes=True,wrong_unit_refused=True,class_field_unused_in_native_type14_branch=True)))
