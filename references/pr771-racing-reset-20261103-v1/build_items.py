"""Original resource/classifier and item-reader proof; no process or live grant."""
from pathlib import Path
import hashlib,json,struct,sys
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
from role_native_replay import Replay,IMAGE_SHA
sys.path.insert(0,str(R))
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.inventory_items import fixture
r=Replay();rows=[]
for t in (714108,714109,714118):
    item=client_data().item(t);raw=item['record'];native=r.alloc(232);r.write(native,raw)
    group=r.call(0x19803a0,0,native);cap=struct.unpack_from('<I',raw,16)[0]
    assert group==(3 if t==714109 else 4)and item['metadata']==2
    cases=[]
    for count in (1,cap):
        body=bytearray.fromhex(fixture()['wire_hex']);struct.pack_into('>i',body,0,t);body[4]=2;struct.pack_into('>i',body,5,count)
        decoded=r.item(body);dto=bytes.fromhex(decoded['dto'])
        assert decoded['ok']==1 and decoded['consumed']==304
        assert (struct.unpack_from('<i',dto)[0],dto[4],struct.unpack_from('<i',dto,5)[0])==(t,2,count)
        cases.append(dict(count=count,ok=True,consumed=304))
    rows.append(dict(template=t,metadata=2,group=group,item_type=item['item_type'],max_stack=cap,record_sha256=hashlib.sha256(raw).hexdigest(),cases=cases))
out=dict(client_sha256=CLIENT_SHA,image_sha256=IMAGE_SHA,items=rows,original_EXE_KOM_modified=False,private_Unicorn=True,live_process=False)
(R/'els_server/data/mount_racing_items.json').write_bytes((json.dumps(out,indent=2)+'\n').encode())
(W/'native-items.json').write_bytes((json.dumps(out,indent=2)+'\n').encode());print(json.dumps(out))
