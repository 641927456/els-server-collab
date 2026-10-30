"""Exact two-leaf successor admission, then the unchanged c63 historical verifier."""
from pathlib import Path
import copy,hashlib,json
from tools.materialize_formal_runtime import bound,plan

REF='references/cache-exact41400-selective-20261030-v1'
CANDIDATE='channels/cache-exact41400-20261030-v1.json'
ACCEPTED='channels/cache-exact41400-accepted-20261030-v1.json'
PARENT='channels/native-shared-repair-accepted-20261030-v1.json'
PARENT_SHA='c63fbed4110c2b6a3f597d305c12971690fe78a6d00c4d2ecc285e039fe001ac'
CANDIDATE_SHA='e0b9e0c432bdcfbb291d701c596b20b54ed7165c3b2ae9211ea154250cc76f35'
LEAVES={'els_server/domain/raid_reward_items.py':'847a7687d8ddc5a7405536eaa327d4e9bc66f337b9814975284f572e63eee7c0',
        'els_server/domain/formal_pve_economy.py':'d3f1ce62b59b61ab2fef348b510f1592509a41e706aa9868001f1deca95b5f5a'}
HEADS={'online':{'release':'cache-exact41400-20261030-v1','formal_manifest_sha256':'b44083c802bcc0e46ec30767bf34c8ed6216b5c4956c2d6bdb5583a4b5bfdf86'},
       'local':{'release':'local-cache-exact41400-20261030-v1','formal_manifest_sha256':'7dd7cab0d08b85c9803e0c96d92109d4d5c2d22d729e47c0104d7f8e40d93b35'}}
COUNTS={'online':1315,'local':1340}
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def encoded(value):return(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')
def digest(value):return hashlib.sha256(encoded(value)).hexdigest()
def entries(profile,mode):
    rows=profile['channels'][mode]['files'];result={r['path']:r for r in rows}
    assert len(rows)==len(result),'Duplicate selected path'
    return result
def accepted_document(candidate):
    """Deterministic metadata only; calling this is not evidence of delivery."""
    result=copy.deepcopy(candidate)
    result.update(name='cache-exact41400-accepted-20261030-v1',candidate=False,
      actual_dual_delivery_verified=True,accepted_heads=copy.deepcopy(HEADS),accepted_delivery=REF+'/accepted-delivery.json')
    result['scope']='Exact immutable catalogue cache and native archive41400 new coin ED0; actual dual acceptance is recorded separately. No GUI/full-clear/public-Boss claim.'
    return result
def validate_delta(parent,candidate,contract):
    assert candidate['candidate']is True and candidate['actual_dual_delivery_verified']is False
    assert 'accepted_heads'not in candidate and 'accepted_delivery'not in candidate
    assert candidate['parent']==PARENT and contract['parent_profile']==dict(path=PARENT,sha256=PARENT_SHA)
    assert contract['candidate_profile']==dict(path=CANDIDATE,sha256=CANDIDATE_SHA)
    assert candidate['delta_business_files']=={'online':2,'local':2}
    assert candidate['new_modules']==candidate['new_files']==candidate['new_hooks']==0 and candidate['new_schema']is False
    assert candidate['client_delta']=={'raw_LOCAL_support_replacements':0,'original_game_EXE_KOM':0}
    assert contract['payload_file_count']==8 and contract['activation']is False
    for mode,count in COUNTS.items():
        old,new=entries(parent,mode),entries(candidate,mode)
        assert len(new)==count and old.keys()==new.keys()
        changes={name for name in old if old[name]!=new[name]};assert changes==set(LEAVES)
        delta={r['path']:r for r in contract['changes'][mode]};assert len(delta)==2 and set(delta)==set(LEAVES)
        for name in LEAVES:
            assert delta[name]['before']==old[name] and delta[name]['after']==new[name]
            assert new[name]['sha256']==LEAVES[name]
            expected=REF+('/cache/source/'+name if name.endswith('raid_reward_items.py')else'/archive41400/'+mode+'/source/'+name)
            assert new[name]['source']==expected and set(new[name])=={'path','size','sha256','source'}
        binding=contract['source_bindings'][mode]
        assert binding['file_count']==count and binding['formal_manifest_sha256']==HEADS[mode]['formal_manifest_sha256']
        assert candidate['channels'][mode]['release']==HEADS[mode]['release']
    return True
def source_contract(root):
    root=Path(root)
    assert sha(root/PARENT)==PARENT_SHA and sha(root/CANDIDATE)==CANDIDATE_SHA
    parent,candidate,contract=read(root/PARENT),read(root/CANDIDATE),read(root/REF/'source-contract.json')
    validate_delta(parent,candidate,contract)
    for mode in COUNTS:plan(root,candidate,mode)
    return contract,candidate,parent
def require_launcher_closure(launcher):
    # Historical fully-cleaned records retain their original contract. A partial
    # storage cleanup is explicit, never projected into a successful cleanup flag.
    if launcher['own_QA_cleanup_verified'] is True:
        assert launcher.get('storage_cleanup_pending',False) is False
        assert launcher.get('global_cleanup_complete',True) is True
        return
    assert launcher['own_QA_cleanup_verified'] is False
    assert launcher['publication_process_and_stage_closed'] is True
    assert launcher['storage_cleanup_pending'] is True
    assert launcher['global_cleanup_complete'] is False
    assert launcher['cleanup_scope']=='Publication processes, slots, locks and remote stage closed; retained local QA caches pending'
    required={'exe','local_archive','local_manifest','friends_archive','friends_manifest','source_profile'}
    assert set(launcher['actual_artifact_sha256'])>=required
    for name in required:
        value=launcher['actual_artifact_sha256'][name]
        assert isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef'for c in value)

def require_receipts(profile,candidate,contract,receipt,launcher=None):
    assert profile['name']=='cache-exact41400-accepted-20261030-v1'
    assert profile['candidate']is False and profile['actual_dual_delivery_verified']is True
    assert profile['accepted_heads']==HEADS and profile['accepted_delivery']==REF+'/accepted-delivery.json'
    for mode in COUNTS:assert entries(profile,mode)==entries(candidate,mode)
    assert receipt['ok']is True and receipt['actual_dual_delivery_verified']is True
    assert receipt.get('synthetic_fixture',False)is False and receipt.get('prospective',False)is False
    assert receipt['candidate_profile_sha256']==CANDIDATE_SHA and receipt['accepted_profile_sha256']==digest(accepted_document(candidate))
    assert receipt['parent_profile_sha256']==PARENT_SHA and receipt['player_database_restore']is False
    assert receipt['private_shop_and_Boss_ED0_qualified']is True and receipt['public_shop_and_41400_entry_qualified']is True
    assert receipt['public_Boss_ED0_verified']is False and receipt['natural_GUI']is False and receipt['natural_battle']is False
    assert receipt['own_QA_cleanup_verified']is True
    assert receipt['launcher_delivery_record']==REF+'/launcher-delivery.json'
    for mode,count in COUNTS.items():
        row=receipt['channels'][mode]
        assert {k:row[k]for k in HEADS[mode]}==HEADS[mode]
        assert row['business_files_verified']==count and row['observation_seconds']>=120
        assert type(row['actual_receipt_sha256'])is str and len(row['actual_receipt_sha256'])==64
    if launcher is None:return True # Business selection and later signed delivery are separate acceptance layers.
    assert launcher['business_delivery_sha256']==digest(receipt)
    assert launcher['ok']is True and launcher['actual_signed_delivery_verified']is True and launcher['V']==46
    assert not launcher.get('prospective',False)and not launcher.get('synthetic_fixture',False)
    assert launcher['source_profile_sha256']==receipt['accepted_profile_sha256'] and launcher['formal_heads']==HEADS
    assert launcher['loaded_business_leaves']==LEAVES and launcher['normal_upgrade_repeat_load_verified']is True
    assert launcher['original_game_EXE_KOM_changed']is False
    require_launcher_closure(launcher)
    assert launcher['observation_seconds']>=120
    assert launcher['dual_receipts']=={m:receipt['channels'][m]['actual_receipt_sha256']for m in COUNTS}
    return True
def verified_current_predecessor(profile,mode,entry,path,*,root=None):
    """Only unchanged proof leaves unwrap; always run the original predecessor."""
    root=Path(root)if root is not None else Path(__file__).resolve().parents[1]
    from tools.verify_shared_repair_inheritance_20261030 import verified_shared_repair_predecessor
    if profile.get('name')=='cache-exact41400-accepted-20261030-v1':
        contract,candidate,parent=source_contract(root)
        assert sha(root/ACCEPTED)==digest(accepted_document(candidate))
        receipt=read(root/REF/'accepted-delivery.json');launcher_path=root/REF/'launcher-delivery.json'
        require_receipts(profile,candidate,contract,receipt,read(launcher_path)if launcher_path.exists()else None)
        before=entries(parent,mode)[entry['path']]
        assert entry==entries(candidate,mode)[entry['path']]==before,'Changed leaf cannot inherit historical proof'
        assert Path(path).resolve()==bound(root,entry['source'])and sha(path)==entry['sha256']
        profile,entry,path=parent,before,bound(root,before['source'])
    return verified_shared_repair_predecessor(profile,mode,entry,path,root=root)
def main():
    root=Path(__file__).resolve().parents[1];contract,candidate,parent=source_contract(root)
    pointer=read(root/'channels/current-engine.json')
    if pointer['profile']==ACCEPTED:
        from tools.materialize_formal_runtime import load_manifest
        selected=load_manifest(root/'channels/current-engine.json',root)
        for mode in COUNTS:
            row=entries(selected,mode)['els_server/storage/seal_quests.py']
            verified_current_predecessor(selected,mode,row,bound(root,row['source']),root=root)
    else:assert pointer['profile']==PARENT,'Unexpected active profile; rebase exact successor'
    print(json.dumps(dict(ok=True,exact_two_source_leaves=True,actual_selected=pointer['profile']==ACCEPTED,
                         launcher_delivery_record_present=(root/REF/'launcher-delivery.json').is_file(),production_actions=0)))
if __name__=='__main__':main()
