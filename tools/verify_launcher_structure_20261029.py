"""Check the exact V44 candidate archive, signatures, source mapping and support."""
from pathlib import Path
import hashlib,importlib.util,json,re,sys
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'launchers/friends-v44'
LOCK_SHA='d2fa18680afd5a374ecef77b964abb760c2b45d19e811f52c1ce39af3b144f00'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_bytes())
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def main():
    assert sha(A/'source-lock.json')==LOCK_SHA,'Unqualified source lock'
    lock=read(A/'source-lock.json');assert sha(A/'build.py')==lock['build_recipe_sha256']
    build=load('structure_launcher_build',A/'build.py');_,files,_=build.inputs()
    prior=read(ROOT/'launchers/friends-v43/source-lock.json')
    old={r['logical_name']:r for r in prior['native_build_inputs']}
    assert lock['parent_source_lock_sha256']==sha(ROOT/'launchers/friends-v43/source-lock.json')
    for row in lock['native_build_inputs']:
        if row['source'].startswith('launchers/friends-v43/'):
            assert row['sha256']==old[Path(row['source']).name]['sha256']
    signed=load('existing_v43_signature_verifier',ROOT/'tools/verify_identity_managed_launcher_20261029.py')
    key=re.search(r'PublicKey = "([^"]+)"',files['AutoUpdate.cs'].read_text('utf-8-sig'))[1]
    release=signed.verify(A/'release.signed.json',key,False);declared=read(A/'release.json')
    assert release['version']==declared['V']==44 and release['sha256']==declared['sha256']==lock['actual_compiled_EXE_sha256']
    assert release['size']==declared['size']
    local=signed.verify(files['resources/structure-local-runtime-files.signed.json'],key)
    previous=signed.verify(files['local-runtime-files.signed.json'],key)
    friends=signed.verify(files['runtime-files.signed.json'],key)
    assert len(friends['files'])==1764 and len(local['files'])==1786 and len(previous['files'])==1779
    assert local['archive']['sha256']==declared['local_payload_sha256']
    rows={r['path']:r for r in local['files']};oldrows={r['path']:r for r in previous['files']}
    delta=read(ROOT/'references/server-structure-20261029-v1/delta.json')['channels']['local']
    assert {p for p in rows.keys()|oldrows.keys()if rows.get(p)!=oldrows.get(p)}==set(delta)|{'local-bootstrap-source.json'}
    metadata=read(A/'local-bootstrap-source.json')
    assert sha(A/'local-bootstrap-source.json')==rows['local-bootstrap-source.json']['sha256']==lock['metadata_sha256']
    target=read(A/'target-source-selection.json');profile=read(ROOT/target['candidate_source_profile'])
    formal={r['path']:{k:r[k]for k in('path','size','sha256')}for r in profile['channels']['local']['files']}
    assert len(formal)==1332 and metadata['source_file_count']==1332
    digest=hashlib.sha256(json.dumps([formal[k]for k in sorted(formal)],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert digest==metadata['source_files_sha256']==target['source_rows_sha256']
    assert metadata['profile']==target['profile'] and metadata['source_formal_manifest_sha256']==target['accepted_heads']['local']['formal_manifest_sha256']
    if (ROOT/target['profile']).exists():assert sha(ROOT/target['profile'])==target['profile_raw_sha256']
    overrides={r['path']:r for r in metadata['support_overrides']}
    assert set(overrides)=={'tools/launch_client.py','tools/client_compatibility_profiles.json'}
    for name,row in formal.items():
        if name=='config/server.toml':
            assert name not in rows and metadata['generated_config_source_sha256']==row['sha256'];continue
        if name in overrides:
            assert overrides[name]['source_sha256']==row['sha256'] and overrides[name]['runtime_sha256']==rows[name]['sha256']
        else:assert rows[name]==row,name
    for addition in metadata['support_additions']:
        assert addition['path']not in formal and rows[addition['path']]['sha256']==addition['runtime_sha256']
    consumer=load('structure_bootstrap_policy',files['resources/structure-local-bootstrap.py'])
    contract=consumer.structure_policy(metadata,rows);assert len(contract['structure_contracts'])==2
    assert consumer.STRUCTURE_PROFILE_HASH==target['profile_raw_sha256']
    # Seven original resources retain their compiled V43 bytes.
    for resource in lock['resources'][:7]:
        if 'logical_name'in resource:assert sha(files[resource['logical_name']])==resource['sha256']
    print(json.dumps(dict(ok=True,V=44,mapped_build_inputs=len(files),resources=9,original_resources=7,
        local_source_files=1332,local_signed_files=1786,RSA_envelopes=4,compiled=False,published=False,
        actual_installation_claimed=False,natural_GUI=False)))
if __name__=='__main__':main()
