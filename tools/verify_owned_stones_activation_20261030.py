"""Exact nine-leaf Git selection after actual private signed V47 qualification.

This record deliberately does not claim a main merge or PUBLIC delivery. Those
require later actual main CI and public first/repeat/closure evidence.
"""
from pathlib import Path,PurePosixPath
import re,copy,hashlib,json

RECORD='references/owned-stones-nine-leaf-selective-20261030-v1/V47-private-activation.json'
REQUIRED_ARTIFACTS={'exe','local_archive','local_manifest','friends_archive','friends_manifest','source_profile'}
ASSETS_LOCK_SHA='3f471406aeb9293e3c36de36ebf4a82f532355e649dd7959aa9d4e4d153cfb9f'
def profile_members(profile):
    sources={};assets={}
    for mode in ('online','local'):
        for row in profile['channels'][mode]['files']:
            assert ('source'in row)!=('asset'in row)
            kind='source'if 'source'in row else'asset';name=row[kind];rel=PurePosixPath(name)
            assert not rel.is_absolute()and ':'not in name and chr(92)not in name and all(s not in ('','.','..')for s in rel.parts)
            if kind=='asset':assert name==row['path']
            rows=sources if kind=='source'else assets;identity=(row['size'],row['sha256'])
            assert name not in rows or rows[name]==identity
            rows[name]=identity
    return sources,assets
def verify_assets_lock(root,profile,record):
    raw=(Path(root)/'runtime-assets.lock.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==record['private_Git']['assets_lock_sha256']==ASSETS_LOCK_SHA
    files=json.loads(raw)['files'];locked={r['path']:(r['size'],r['sha256'])for r in files};assert len(locked)==len(files)
    for name,identity in profile_members(profile)[1].items():assert locked[name]==identity

def validate_activation(profile,receipt,record):
    from tools import verify_owned_stones_nine_archive_20261030 as nine
    assert record['schema']==1 and record['scope']=='Actual private signed V47 qualification; Git selection candidate; PUBLIC delivery pending'
    assert record['ok']is True and record['version']==47 and record['actual_private_signed_qualification']is True
    assert record['profile']==nine.PROFILE and record['profile_sha256']==receipt['accepted_profile_sha256']==nine.old.digest(profile)
    assert record['formal_heads']==nine.HEADS and record['source_binding_sha256']=='a2b1ff7e286c4de294b9b4a50fd3be0400d3d22248fde686932c3b959b035647'
    assert record['base_main']=='7a7efa34947dee63760008cc78c2579886ef7b81'
    for field in ('main_merge_claimed','public_launcher_delivered','public_QA_claimed','natural_GUI_claimed','natural_battle_claimed','original_game_EXE_KOM_changed'):assert record[field]is False
    assert record['launcher_delivery_pending']is True
    assert record['private_Git']['profile_sha256']==record['profile_sha256'] and record['private_Git']['actual_main_merge_claimed']is False
    for field in ('commit','tree'):assert re.fullmatch('[a-f0-9]{40}',record['private_Git'][field])
    sources,assets=profile_members(profile);pg=record['private_Git']
    assert type(pg['full_profile_source_members'])is int and pg['full_profile_source_members']==len(sources)
    assert type(pg['full_profile_asset_members'])is int and pg['full_profile_asset_members']==len(assets)
    assert pg['assets_signed_archive_verified']is True and pg['assets_lock_sha256']==ASSETS_LOCK_SHA
    assert set(record['actual_artifact_sha256'])==REQUIRED_ARTIFACTS and record['actual_artifact_sha256']['source_profile']==record['profile_sha256']
    for value in list(record['actual_artifact_sha256'].values())+[record['private_qualification_sha256'],record['independent_private_review_sha256'],record['build_sha256'],record['final_QA_binding_sha256'],record['private_Git_input_sha256']]:assert isinstance(value,str)and re.fullmatch('[a-f0-9]{64}',value)
    assert isinstance(record['private_evidence_sha256'],dict)and record['private_evidence_sha256']
    for value in record['private_evidence_sha256'].values():assert re.fullmatch('[a-f0-9]{64}',value)
    return True

def verify_active_pointer(root,profile,receipt):
    from tools import verify_owned_stones_nine_archive_20261030 as nine
    root=Path(root);record=nine.read(root/RECORD);validate_activation(profile,receipt,record);verify_assets_lock(root,profile,record)
    assert nine.read(root/'channels/current-engine.json')==dict(format=1,profile=nine.PROFILE,accepted=nine.HEADS)
    return record

def verified_nine_predecessor(profile,mode,entry,path,*,root=None):
    from tools import verify_owned_stones_nine_archive_20261030 as nine
    root=Path(root)if root is not None else Path(__file__).resolve().parents[1]
    nine.verify(root)
    raw=nine.read(root/nine.PROFILE)
    # load_manifest(current-engine) adds only the accepted head projection to
    # each raw channel. Preserve every other raw field and exact source row.
    resolved=copy.deepcopy(raw)
    assert raw['accepted_heads']==nine.HEADS and set(raw['channels'])==set(nine.HEADS)
    for channel,head in nine.HEADS.items():resolved['channels'][channel].update(head)
    assert profile==raw or profile==resolved,'Exact raw or resolved selected nine profile required'
    parent=nine.read(root/nine.PARENT);after=nine.entries(profile,mode);before=nine.entries(parent,mode)
    assert entry==after[entry['path']]==before[entry['path']],'Changed nine leaf cannot inherit historical proof'
    assert Path(path).resolve()==nine.old.bound(root,entry['source'])and nine.sha(path)==entry['sha256']
    # Reuse every two-leaf/c63/native predecessor assertion on the exact retained
    # profile and original source locator, never on a reconstructed replacement.
    return nine.old.verified_current_predecessor(parent,mode,before[entry['path']],nine.old.bound(root,before[entry['path']]['source']),root=root)
