from pathlib import Path
import sys,struct,json
HOME=Path(__file__).resolve().parent;sys.path.insert(0,str(HOME))
import test_boxes as fixture
sys.path.insert(0,'G:/els/tools')
from verify_fixed_cubes_native import CubeReplay
from els_server.protocol.ice_messages import preview_ack
from els_server.domain.owned_reward_boxes import outputs_for
r=CubeReplay();rows=[]
for template,cls in ((723618,150),(135666,177),(723687,196),(117542,1)):
 x=fixture.Boxes();x.setUp()
 try:
  x.career(cls);box=x.grant(template);outputs=outputs_for(template,x.account.character())
  choices=(outputs[-1]['template'],)if template==723687 else()
  preview=r.preview(preview_ack(0,template,selection_count=int(bool(choices)),entries=[(e['template'],0,e['quantity'])for e in outputs]).payload)
  assert preview['template']==template and len(preview['entries'])==len(outputs)
  answer=x.use(box,f'native-{template}',choices=choices)
  inventory=r.inventory(fixture.ack(answer,0xad8).payload);result=r.result(fixture.ack(answer,0x197).payload)
  assert result['result']==0 and result['items']==inventory
  assert len(result['rewards'])==(1 if choices else len(outputs))
  expected=1 if choices else sum(e['quantity']for e in outputs)
  assert sum(i['count']for i in inventory if i['uid'])==expected
  if template==135666:assert len([i for i in inventory if i['uid']and i['date']])==12
  rows.append(dict(template=template,unit_class=cls,preview_entries=len(preview['entries']),reward_entries=len(result['rewards']),result_items=len(inventory),original_full_reader=True))
 finally:x.doCleanups()
(HOME/'native-result.json').write_text(json.dumps(dict(ok=True,live_process=False,image_sha256='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229',rows=rows),indent=2),encoding='utf8')
print(json.dumps(dict(ok=True,rows=rows)))
