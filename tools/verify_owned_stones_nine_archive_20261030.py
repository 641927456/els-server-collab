"""Nine-leaf actual business archive; V46/current-engine remain exact two-leaf predecessors."""
from pathlib import Path
import hashlib, json, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.materialize_formal_runtime import plan
from tools import verify_cache_exact41400_inheritance_20261030 as old

REF='references/owned-stones-nine-leaf-selective-20261030-v1'
PARENT=old.ACCEPTED
PARENT_SHA='951c6b5fbf13c6f7e9eda825c9d13e3e601b4bf8325f876dce04b572d6f08c2c'
PROFILE='channels/owned-stones-nine-leaf-accepted-20261030-v1.json'
HEADS={'online':{'release':'owned-stones-nine-leaf-20261030-v1','formal_manifest_sha256':'5673f1b344ca6a30e1e8741f69a730544ef5798bb8a926ea171a4a40406da5a6'},'local':{'release':'local-owned-stones-nine-leaf-20261030-v1','formal_manifest_sha256':'965f336f1f5f940746eedf51c1c94f57c60abbdffc50e78c025e1da3d4ff3558'}}
COUNTS={'online':1316,'local':1341}
ADDED='els_server/data/select_cubes_owned_magic_native.json'
CHANGED={'els_server/data/additional_magic_stones.json','els_server/data/select_cubes.json','els_server/data/select_cubes.manifest.json',ADDED,'els_server/domain/additional_magic_stones.py','els_server/domain/inventory_items.py','els_server/domain/select_cubes.py','els_server/protocol/spell_socket_messages.py','els_server/storage/fixed_cubes.py'}
EXACT_LEAVES = {'online': {'els_server/data/additional_magic_stones.json': {'size': 23944, 'sha256': '4d09c493ac6fde1bc7b5d7be774d09ab853b340f1d5152bca757e100e0e44907'}, 'els_server/data/select_cubes.json': {'size': 10121, 'sha256': '03d8b2d2a22a46ab1dfe2b3b5e128433e24f63ef24d6d8ac59d650d31de85077'}, 'els_server/data/select_cubes.manifest.json': {'size': 160, 'sha256': '98052167a60091b7d8e9d7fcfeeac74dd2788e9667d62e129268ebdcf9720e00'}, 'els_server/data/select_cubes_owned_magic_native.json': {'size': 8441, 'sha256': '96362633694fbff9101ea02e55a320a84e9b3e60965521c71473cc84fad588cf'}, 'els_server/domain/additional_magic_stones.py': {'size': 1775, 'sha256': '20c65a204fec9ebdfe9265195d812e780b67665758841985d58891783944279c'}, 'els_server/domain/inventory_items.py': {'size': 74075, 'sha256': '80c1edda1915939326341e0b5988205d48da4b51de7a468d528d16fbd0c0f122'}, 'els_server/domain/select_cubes.py': {'size': 4136, 'sha256': '786ae0bbf968e7708881b1605f5442a4ed89b4389eba2e3e94184c83661f6ded'}, 'els_server/protocol/spell_socket_messages.py': {'size': 1542, 'sha256': '0cb94626a4fd80a087748f8785cf7acdd44134e45323cb92e0cdd46bf186d2a2'}, 'els_server/storage/fixed_cubes.py': {'size': 8841, 'sha256': '9d291013c158354df4189ced34097f3531827667b4f56cf4ac86ab852df60a14'}}, 'local': {'els_server/data/additional_magic_stones.json': {'size': 23944, 'sha256': '4d09c493ac6fde1bc7b5d7be774d09ab853b340f1d5152bca757e100e0e44907'}, 'els_server/data/select_cubes.json': {'size': 10121, 'sha256': '03d8b2d2a22a46ab1dfe2b3b5e128433e24f63ef24d6d8ac59d650d31de85077'}, 'els_server/data/select_cubes.manifest.json': {'size': 160, 'sha256': '98052167a60091b7d8e9d7fcfeeac74dd2788e9667d62e129268ebdcf9720e00'}, 'els_server/data/select_cubes_owned_magic_native.json': {'size': 8441, 'sha256': '96362633694fbff9101ea02e55a320a84e9b3e60965521c71473cc84fad588cf'}, 'els_server/domain/additional_magic_stones.py': {'size': 1775, 'sha256': '20c65a204fec9ebdfe9265195d812e780b67665758841985d58891783944279c'}, 'els_server/domain/inventory_items.py': {'size': 73920, 'sha256': 'bb94e23b06684b9343951aee38b2709d3ef5a5cc7bcb92623b4f9e6528be0f9d'}, 'els_server/domain/select_cubes.py': {'size': 4136, 'sha256': '786ae0bbf968e7708881b1605f5442a4ed89b4389eba2e3e94184c83661f6ded'}, 'els_server/protocol/spell_socket_messages.py': {'size': 1542, 'sha256': '0cb94626a4fd80a087748f8785cf7acdd44134e45323cb92e0cdd46bf186d2a2'}, 'els_server/storage/fixed_cubes.py': {'size': 8841, 'sha256': '9d291013c158354df4189ced34097f3531827667b4f56cf4ac86ab852df60a14'}}}
read=old.read;sha=old.sha;encoded=old.encoded;entries=old.entries

def validate(parent,profile,contract,receipt):
    assert profile['name']=='owned-stones-nine-leaf-accepted-20261030-v1' and profile['parent']==PARENT
    assert profile['candidate']is False and profile['actual_dual_delivery_verified']is True
    assert profile['accepted_heads']==HEADS and profile['accepted_delivery']==REF+'/accepted-delivery.json'
    assert profile['delta_business_files']=={'online':9,'local':9} and profile['new_files']==1 and profile['new_modules']==0
    assert profile['new_hooks']==0 and profile['new_schema']is False and profile['client_delta']=={'raw_LOCAL_support_replacements':0,'original_game_EXE_KOM':0}
    assert profile['launcher_delivery_pending']is True and profile['signed_launcher_version_claimed']is None
    assert contract['parent_profile']==dict(path=PARENT,sha256=PARENT_SHA) and contract['activation']is False
    assert contract['source_binding_sha256']=='a2b1ff7e286c4de294b9b4a50fd3be0400d3d22248fde686932c3b959b035647'
    assert contract['payload_file_count']==10 and contract['business_heads']==HEADS
    sources=set()
    for mode,count in COUNTS.items():
        before,after=entries(parent,mode),entries(profile,mode)
        assert len(after)==count and set(after)-set(before)=={ADDED} and not(set(before)-set(after))
        assert {n for n in after if after[n]!=before.get(n)}==CHANGED
        delta={r['path']:r for r in contract['changes'][mode]};assert set(delta)==CHANGED
        for n in after:
            if n in CHANGED:
                assert delta[n]['before']==before.get(n) and delta[n]['after']==after[n]
                assert {k:after[n][k] for k in ('size','sha256')}==EXACT_LEAVES[mode][n]
                expected=REF+('/'+mode+'/source/'if n.endswith('/inventory_items.py')else'/shared/source/')+n
                assert after[n]['source']==expected and set(after[n])=={'path','size','sha256','source'}
                sources.add(expected)
            else:assert after[n]==before[n]
        assert profile['channels'][mode]['release']==HEADS[mode]['release']
        assert profile['channels'][mode]['parent_release']==parent['channels'][mode]['release']
        for name,digest in old.LEAVES.items():assert after[name]==before[name] and after[name]['sha256']==digest
        r=receipt['channels'][mode];assert {k:r[k]for k in HEADS[mode]}==HEADS[mode]
        assert r['business_files_verified']==count and r['observation_seconds']>=120 and len(r['actual_receipt_sha256'])==64
    assert len(sources)==10
    assert receipt['ok']is True and receipt['actual_dual_delivery_verified']is True and receipt['prospective']is False and receipt['synthetic_fixture']is False
    assert receipt['synthetic_receipt']is False and receipt['controlled_QA_fixture_used']is True
    assert receipt['fixture_scope']=='Owned-only held historical136186, full role5/164/99/1/1, materials/box and2000000ED; not natural acquisition or initial identification'
    assert receipt['synthetic_fixture_field_means']=='Receipt is actual rather than synthetic success placeholder; controlled fixture was used'
    assert receipt['accepted_profile_sha256']==old.digest(profile) and receipt['parent_profile_sha256']==PARENT_SHA
    assert receipt['source_binding_sha256']==contract['source_binding_sha256']
    for k in ('private_nine_leaf_App_qualified','public_eight_transactions_and_cold_qualified','own_QA_cleanup_verified'):assert receipt[k]is True
    for k in ('player_database_restore','natural_GUI','natural_battle','initial_136186_pool_qualified','natural_item_acquisition_qualified','new_signed_launcher_delivered'):assert receipt[k]is False
    assert receipt['new_signed_launcher_version']is None and receipt['public_economic_requests']==8
    assert receipt['current_engine_activated']is False and receipt['launcher_delivery_pending']is True
    return True

def verify(root):
    root=Path(root);assert sha(root/PARENT)==PARENT_SHA
    parent,profile,contract,receipt=read(root/PARENT),read(root/PROFILE),read(root/REF/'source-contract.json'),read(root/REF/'accepted-delivery.json')
    validate(parent,profile,contract,receipt)
    # Preserve every predecessor assertion. Current remains the V46-compatible accepted profile.
    previous_contract,candidate,grandparent=old.source_contract(root)
    previous_receipt=read(root/old.REF/'accepted-delivery.json');launcher=read(root/old.REF/'launcher-delivery.json')
    old.require_receipts(parent,candidate,previous_contract,previous_receipt,launcher)
    assert set(launcher['actual_artifact_sha256'])>={'exe','local_archive','local_manifest','friends_archive','friends_manifest','source_profile'}
    assert launcher['source_profile_sha256']==PARENT_SHA and launcher['V']==46
    assert read(root/'channels/current-engine.json')==dict(format=1,profile=PARENT,accepted=old.HEADS)
    for mode in COUNTS:plan(root,profile,mode)
    return dict(ok=True,actual_business_archive=True,current_engine_activated=False,launcher_for_nine_leaf_pending=True,V46_is_two_leaf_only=True)

if __name__=='__main__':print(json.dumps(verify(Path(__file__).resolve().parents[1])))
