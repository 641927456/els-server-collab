"""Reuse unchanged proofs; execute original readers/classifier for new rows."""
from pathlib import Path
import hashlib,json,struct,sys
W=Path(__file__).resolve().parent;R=W.parents[1];C=W/'candidate';sys.dont_write_bytecode=True
sys.path[:0]=[str(C),str(R/'tools'),str(R/'tools/pylibs')]
from role_native_replay import Replay,IMAGE_SHA
P=Path(json.loads((W/'update-binding.json').read_bytes())['parent_root'])
seed=json.loads((C/'analysis/client-6c6b5180/item-body-candidate.json').read_bytes())
groups=[('analysis/shop-listing-20261015/fashion-bundles.candidate.json',
         'analysis/shop-listing-20261015/fashion-bundles.json','analysis/shop-listing-20261015/fashion-bundles-body-proof.json','definitions'),
        ('analysis/client-6c6b5180/extended-shop-catalog.json',
         'analysis/client-6c6b5180/extended-shop-catalog.json','analysis/client-6c6b5180/extended-shop-body-proof.json','offers')]
executed=0;reused=0;reports=[]
for input_path,final_path,proof_path,key in groups:
    content=(C/input_path).read_bytes();c=json.loads(content)
    old=json.loads((P/final_path).read_bytes());old_defs={r['template']:r for r in old[key]}
    old_proof=json.loads((P/proof_path).read_bytes());old_rows={r['template']:r for r in old_proof['rows']}
    proof=[];new_count=0
    for row in c[key]:
        t=row['template']
        if t in old_defs:
            assert row==old_defs[t],t
            proof.append(old_rows[t]);reused+=1;continue
        if executed%128==0:replay=Replay()
        wire=bytearray.fromhex(seed['wire_hex']);values={0:t,4:row['metadata'],5:1}
        for f in seed['fields']:
            offset=int(f['offset'],0)
            if offset in values:
                width=1 if offset==4 else 4
                wire[f['wire_offset']:f['wire_offset']+width]=values[offset].to_bytes(width,'big')
        decoded=replay.item(bytes(wire));assert decoded['ok']==1 and decoded['consumed']==len(wire)==304,t
        dto=bytes.fromhex(decoded['dto'])
        for f in seed['expected_memory']:
            expected=values[f['offset']].to_bytes(f['size'],'little')if f['offset']in values else bytes.fromhex(f['hex'])
            assert dto[f['offset']:f['offset']+f['size']]==expected,(t,f)
        vectors=[struct.unpack_from('<QQQ',dto,o)for o in(0xd,*[0x25+i*0x18 for i in range(33)])]
        assert all(a==b and a<=cap for a,b,cap in vectors),t
        ptr=replay.alloc(232);replay.write(ptr,bytes.fromhex(row['record_hex']))
        group=replay.call(0x19803a0,0,ptr);assert group==row['group'],(t,group,row['group'])
        proof.append(dict(template=t,ok=1,consumed=304,fields_match=True,vectors_empty=True,native_template_id=t,
            native_group=group,private_data_item=dict(template_id=t,metadata=row['metadata'],count=1),
            applied_to_game=False,no_reward_persistence=True,record_sha256=hashlib.sha256(bytes.fromhex(row['record_hex'])).hexdigest(),
            evidence='OriginalD9A550/19803A0 in private Unicorn memory'))
        executed+=1;new_count+=1
        if executed%1024==0:print('Original native rows verified',executed,flush=True)
    (C/final_path).write_bytes(content)
    result=dict(client_sha256=c['client_sha256'],catalog_sha256=hashlib.sha256(content).hexdigest(),all_passed=True,count=len(proof),
        image_sha256=IMAGE_SHA,new_original_reader_cases=new_count,reused_unchanged_cases=len(proof)-new_count,
        live_process=False,rows=proof)
    (C/proof_path).write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n','utf8')
    reports.append({k:v for k,v in result.items()if k!='rows'})
(W/'native-body-result.json').write_text(json.dumps(dict(ok=True,new_cases=executed,reused_cases=reused,reports=reports),indent=2)+'\n','utf8')
print(json.dumps(dict(ok=True,new_cases=executed,reused_cases=reused)))
