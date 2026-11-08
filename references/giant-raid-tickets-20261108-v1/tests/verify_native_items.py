"""Original DTO reader and native bag classifier, in private Unicorn memory."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
R=Path(json.loads((W/'ticket-parent.json').read_bytes())['runtime'])
sys.path[:0]=[str(R),str(Path('G:/els/tools')),str(Path('G:/els/tools/launcher_testdeps')),str(R/'tools/pylibs')]
import els_server.domain
els_server.domain.__path__.insert(0,str(W/'candidate/els_server/domain'))
from els_server.game_data import client_data
from els_server.domain.inventory_items import item_body,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.dungeon_ticket_shop import TEMPLATES
from role_native_replay import Replay,IMAGE_SHA
replay=Replay();rows=[]
for template in sorted(TEMPLATES):
    meta=VERIFIED_TEMPLATES[template]
    wire=item_body(dict(uid=880001,template=template,metadata=meta,count=1,group=4,slot=0))
    decoded=replay.item(wire);dto=bytes.fromhex(decoded['dto'])
    assert decoded['ok']==1 and decoded['consumed']==len(wire)==304
    assert struct.unpack_from('<I',dto)[0]==template and dto[4]==meta and struct.unpack_from('<I',dto,5)[0]==1
    raw=client_data().item(template)['record'];p=replay.alloc(len(raw));replay.write(p,raw)
    assert replay.call(0x19803a0,0,p)==TEMPLATE_BAG_GROUPS[template]==4
    rows.append(dict(template=template,name=client_data().item(template)['name'],metadata=meta,consumed=304,group=4,record_sha256=hashlib.sha256(raw).hexdigest()))
result=dict(passed=True,image_sha256=IMAGE_SHA,rows=rows,live_process=False,applied_to_game=False)
(W/'ticket-native-readers.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(dict(passed=True,original_native_reader_cases=len(rows),live_process=False)))
