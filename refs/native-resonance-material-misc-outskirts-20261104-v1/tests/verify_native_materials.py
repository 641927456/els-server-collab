import runtime_inputs
import hashlib,json,sys
from pathlib import Path
W=Path(__file__).resolve().parent;R=Path('G:/els');sys.path.insert(0,str(R/'tools'))
from els_server.domain.inventory_items import item_body
from verify_manufacture_material_native import MaterialReplay,IMAGE_SHA
items=[dict(uid=0x100000000+i,template=t,metadata=2,group=4,slot=i,count=count)for i,(t,count)in enumerate(((711763,1),(711763,2),(711763,1000),(711785,1),(711785,1000),(118191,1),(118191,300),(118250,1),(118250,1000)),1)]
r=MaterialReplay(items);rows=[]
for item in items:
 body=item_body(item);parsed=r.item(body)
 assert parsed['ok']==1 and parsed['consumed']==304
 rows.append(dict(template=item['template'],count=item['count'],body_sha256=hashlib.sha256(body).hexdigest(),original_reader_ok=True,consumed=parsed['consumed'],constructor_executed=True))
for template,total in((711763,1003),(711785,1001),(118191,301),(118250,1001)):
 assert r.count(template)==total;count,candidates=r.candidates(template);assert count==total
result=dict(passed=True,runtime_sha256=IMAGE_SHA,offline_original_machine_code=True,live_process_access=False,rows=rows,native_material_enumeration=True)
(W/'native-material-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False))
