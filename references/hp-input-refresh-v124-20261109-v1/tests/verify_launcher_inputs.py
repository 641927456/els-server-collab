"""Validate archived launcher inputs without executing or rebuilding the launcher.

Envelope SHA is checked; this is not an independent RSA verification.
"""
from pathlib import Path,PurePosixPath
import base64,hashlib,json
ROOT=Path(__file__).resolve().parents[1]
sha=lambda raw:hashlib.sha256(raw).hexdigest()
c=json.loads((ROOT/'launcher-build-contract.json').read_bytes())
s=json.loads((ROOT/'source-contract.json').read_bytes())
assert c['version']==124 and c['parent_version']==123
assert c['compiled_input_count']==len(c['compiled_input_inventory'])==146
assert c['inherited_unchanged_input_count']==143
assert len(c['compiled_changed_inputs'])==c['source_files_included']==3
assert {r['path'] for r in c['compiled_changed_inputs']}=={
 'AutoUpdate.cs','UIScrollRuntimeCohort.cs','resources/ui-scroll-signedFriends.signed.json'}
for name,row in c['compiled_input_inventory'].items():
 rel=PurePosixPath(name)
 assert not rel.is_absolute() and '..' not in rel.parts
 assert row['size']>0 and len(row['sha256'])==64
for r in c['compiled_changed_inputs']:
 raw=(ROOT/'launcher-source'/r['path']).read_bytes()
 assert {'size':len(raw),'sha256':sha(raw)}==r['after']==c['compiled_input_inventory'][r['path']]
 assert r['before']!=r['after']
for r in c['resource_mappings']:
 assert c['compiled_input_inventory'][r['path']]['sha256']==r['sha256']
assert len({r['name'] for r in c['resource_mappings']})==len(c['resource_mappings'])==101
raw=(ROOT/'launcher-source/resources/ui-scroll-signedFriends.signed.json').read_bytes()
assert sha(raw)==c['signed_manifest_sha256']
envelope=json.loads(raw);assert set(envelope)=={'payload','signature'} and envelope['signature']
payload=json.loads(base64.b64decode(envelope['payload'],validate=True))
assert payload['archive']['sha256']==c['runtime_archive']['sha256']
runtime={r['path']:r for r in payload['files']}
assert len(runtime)==len(payload['files'])==c['runtime_file_count']==2896
assert c['preserved_runtime_file_count']==2893
assert c['runtime_engine_changes']==1 and c['runtime_support_changes']==2
assert len(c['combined_runtime_delta'])==3
for rel,r in c['combined_runtime_delta'].items():assert runtime[rel]['sha256']==r['after']
for r in s['files']:assert runtime[r['path']]['sha256']==r['sha256']
other=c['companion_source_reference']
assert other['issue']==973 and runtime[other['runtime_path']]['sha256']==other['sha256']
cohort=(ROOT/'launcher-source/UIScrollRuntimeCohort.cs').read_text(encoding='utf-8-sig')
assert c['runtime_archive']['sha256'] in cohort and c['signed_manifest_sha256'] in cohort
assert runtime['tools/client_compatibility_profiles.json']['sha256'] in cohort
assert 'public const int Version = 124;' in (ROOT/'launcher-source/AutoUpdate.cs').read_text(encoding='utf-8-sig')
print(json.dumps({'ok':True,'compiled_inventory':146,'archived_changed_inputs':3,
 'inherited_input_hash_references':143,'resource_mappings':101,'runtime_delta_bindings':3,
 'public_release_or_upgrade_verified':False,'game_started':False,'network_used':False}))
