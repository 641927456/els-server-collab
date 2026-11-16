from pathlib import Path
import hashlib,json,os,struct,sys
K=Path(__file__).resolve().parent;R=Path('G:/els');S=K/'reward-source-v1'
sys.dont_write_bytecode=True;sys.path[:0]=[str(S),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
os.environ['ELS_RUNTIME_IMAGE']=str(R/'analysis/client-6c6b5180/x2-runtime.bin')
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,item_body
from els_server.domain.activity_2026_stack_policy import effective_stack
from role_native_replay import Replay,IMAGE_SHA
source=json.loads((K/'original-pet-trainer-exchange-v1.json').read_bytes())
box=json.loads((K/'native-trainer-resurrection-box-v1.json').read_bytes())
recipes=source['matching_calls'];assert len(recipes)==7
rows=[];r=Replay();proof=[]
for t in sorted({a['arguments'][4]for a in recipes}):
    d=client_data().item(t);record=r.alloc(len(d['record']));r.write(record,d['record']);group=r.call(0x19803a0,0,record)&0xffffffff
    raw_stack=struct.unpack_from('<I',d['record'],16)[0]
    cap=TEMPLATE_MAX_STACKS[t]if t in TEMPLATE_MAX_STACKS else effective_stack(raw_stack)
    shape=(d['metadata'],group,cap)
    if t in VERIFIED_TEMPLATES:assert shape==(VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t],TEMPLATE_MAX_STACKS[t])
    VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t],TEMPLATE_MAX_STACKS[t]=shape
    for count in(1,cap):
        wire=item_body(dict(uid=1001001,template=t,metadata=d['metadata'],count=count,group=group,slot=0));read=r.item(wire);dto=bytes.fromhex(read['dto'])
        assert read['ok']==1 and read['consumed']==len(wire)==304 and struct.unpack_from('<I',dto)[0]==t and struct.unpack_from('<i',dto,5)[0]==count
    rows.append(dict(template=t,name=d['name'],metadata=d['metadata'],group=group,max_stack=cap,raw_max_stack=raw_stack,item_type=d['item_type'],record_sha256=hashlib.sha256(d['record']).hexdigest()))
    proof.append(dict(template=t,native_group=group,ok=1,consumed=304,counts=[1,cap]))
data=dict(policy='pet-trainer-original-exchange-20261106-v1',client_sha256=CLIENT_SHA,catalog_sha256=client_data().manifest['catalog_sha256'],
          definitions=rows,recipes=recipes,towns=json.loads((S/'els_server/data/pvp_material_exchange.json').read_bytes())['towns'],
          exchange_source=dict(path=Path(source['source']).relative_to(R).as_posix(),sha256=source['sha256']),resurrection_box=box)
dest=S/'els_server/data/pet_trainer_exchange.json';dest.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n','utf8')
report=dict(ok=True,actual_native_code=True,native_Game=False,production_database_access=False,image_sha256=IMAGE_SHA,cases=proof,data_sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
(K/'trainer-readers-native-v1.json').write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(report))
