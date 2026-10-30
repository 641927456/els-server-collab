"""Admit only the exact delivered Source31 successor to historical source checks."""
from pathlib import Path
import hashlib,json
from tools.materialize_formal_runtime import bound,plan
NAME='native-shared-repair-20261030-v1'
ACCEPTED='channels/native-shared-repair-accepted-20261030-v1.json'
PARENT='channels/server-structure-accepted-20261029-v1.json'
CANDIDATE='channels/native-shared-repair-20261030-v1.json'
REF='references/'+NAME
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def entries(profile,mode):return {r['path']:r for r in profile['channels'][mode]['files']}
def source_contract(root):
    """Source-only preparation check; deliberately confers no acceptance."""
    contract=read(root/REF/'selected-source-contract.json')
    assert sha(root/CANDIDATE)==contract['candidate_profile_sha256']
    assert sha(root/PARENT)==contract['parent_profile_sha256']
    assert sha(root/REF/'delta.json')==contract['delta_sha256']
    candidate=read(root/CANDIDATE);parent=read(root/PARENT);delta=read(root/REF/'delta.json')
    assert candidate['candidate']is True and candidate['actual_dual_delivery_verified']is False
    assert candidate['parent']==delta['parent']==PARENT
    assert delta['parent_sha256']==contract['parent_profile_sha256']
    for mode,count in [('online',28),('local',31)]:
        old,new=entries(parent,mode),entries(candidate,mode)
        actual={p for p in old.keys()|new.keys()if old.get(p)!=new.get(p)}
        assert actual==set(delta['channels'][mode])and len(actual)==count
        assert len(new)==contract['business_files'][mode]and len(set(new)-set(old))==8
        for p,row in delta['channels'][mode].items():
            assert (old[p]['sha256']if p in old else None)==row['before_sha256']
            assert all(new[p][k]==row[k]for k in('source','size','sha256'))
        plan(root,candidate,mode)
    return contract,candidate,parent
def verified_shared_repair_predecessor(profile,mode,entry,path,*,root=None):
    """Retain the original structure assertions after an exact, real receipt gate."""
    if profile.get('name')!='native-shared-repair-accepted-20261030-v1':
        return profile,entry,path
    root=Path(root)if root is not None else Path(__file__).resolve().parents[1]
    contract,candidate,parent=source_contract(root)
    assert profile.get('candidate')is False and profile.get('actual_dual_delivery_verified')is True
    assert sha(root/ACCEPTED)==contract['prospective_accepted_profile_sha256']
    accepted=read(root/ACCEPTED)
    assert accepted['accepted_delivery']==REF+'/accepted-delivery.json'
    assert profile['accepted_heads']==accepted['accepted_heads']==contract['accepted_heads']
    for channel in('online','local'):
        assert entries(profile,channel)==entries(accepted,channel)==entries(candidate,channel)
    receipt_path=root/REF/'accepted-delivery.json'
    assert receipt_path.is_file(),'Source31 actual accepted-delivery receipt is required'
    receipt=read(receipt_path)
    assert receipt['ok']is True and receipt['actual_dual_delivery_verified']is True
    assert not receipt.get('synthetic_fixture',False)and not receipt.get('prospective',False)
    assert receipt['candidate_manifest_sha256']==contract['candidate_profile_sha256']
    assert receipt['accepted_profile_sha256']==contract['prospective_accepted_profile_sha256']
    assert receipt['C3_App_and_compatible_OS_qualified']is True
    assert receipt['signed_packages_qualified']is True and receipt['own_test_cleanup_verified']is True
    assert receipt['player_database_restore']is False
    for channel in('online','local'):
        actual=receipt['channels'][channel]
        assert {k:actual[k]for k in('release','formal_manifest_sha256')}==contract['accepted_heads'][channel]
        assert actual['verified_business_files']==contract['business_files'][channel]
        assert actual['observation_seconds']>=120
    for family,expected in contract['support_families'].items():
        actual=receipt['production_support_loading'][family]
        assert actual['verified']is True and actual['loaded_sha256']==expected
    previous=entries(parent,mode)[entry['path']]
    assert entry==entries(candidate,mode)[entry['path']]==previous,'Historical proof leaf changed in Source31'
    assert Path(path).resolve()==bound(root,entry['source'])
    assert sha(Path(path))==entry['sha256']
    return parent,previous,bound(root,previous['source'])
