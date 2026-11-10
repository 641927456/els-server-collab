"""Execute the original item classifier and reader in private Unicorn memory."""
from qa_environment import F,R
import hashlib,json,struct,sys,time,traceback
from els_server.domain.inventory_items import item_body,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.consumables import catalog
sys.path.insert(0,str(R/'tools'))
from role_native_replay import Replay,IMAGE_SHA
report=dict(ok=False,live_process_access=False,client_changes=0,production_database_access=False,
 image_sha256=IMAGE_SHA,template=710012,cases=[])
try:
    raw=bytes.fromhex(catalog()[710012]['record_hex']);replay=Replay();p=replay.alloc(len(raw));replay.write(p,raw)
    group=replay.call(0x19803a0,0,p)
    assert(group,VERIFIED_TEMPLATES[710012],TEMPLATE_BAG_GROUPS[710012])==(6,2,6)
    requested=tuple(map(int,sys.argv[1:]))if sys.argv[1:]else(1,99,500,999)
    for count in requested:
        body=item_body(dict(uid=1001001,template=710012,metadata=2,group=6,slot=0,count=count))
        result=replay.item(body);dto=bytes.fromhex(result['dto'])
        assert result['ok']==1 and result['consumed']==len(body)==304
        assert(struct.unpack_from('<i',dto)[0],dto[4],struct.unpack_from('<i',dto,5)[0])==(710012,2,count)
        report['cases'].append(dict(count=count,ok=1,consumed=304,wire_sha256=hashlib.sha256(body).hexdigest()))
    report.update(ok=True,native_group=group,record_sha256=hashlib.sha256(raw).hexdigest(),
        classifier_RVA='19803A0',reader_RVA='D9A550',constructor_RVA='7DD4F0')
except BaseException:report['failure']=traceback.format_exc()
report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((F/'source-v1').rglob('*'))if p.is_file()}
(F/('native-item-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps(report,ensure_ascii=False));raise SystemExit(not report['ok'])
