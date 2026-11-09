"""Check the three archived inputs against their full build/resource contract.

No executable, signature private key, network or updater execution is needed.
Envelope SHA identity is checked; this is not an independent RSA verifier.
"""
from pathlib import Path, PurePosixPath
import base64
import hashlib
import json

AREA = Path(__file__).resolve().parents[1]
contract = json.loads((AREA / 'launcher-build-contract.json').read_bytes())
sources = json.loads((AREA / 'source-contract.json').read_bytes())
assert contract['version'] == 123 and contract['parent_version'] == 122
inventory = contract['compiled_input_inventory']
assert len(inventory) == contract['compiled_input_count'] == 146
assert contract['inherited_unchanged_input_count'] == 143
assert len(contract['compiled_changed_inputs']) == contract['source_files_included'] == 3
expected = {'AutoUpdate.cs', 'UIScrollRuntimeCohort.cs', 'resources/ui-scroll-signedFriends.signed.json'}
assert {x['path'] for x in contract['compiled_changed_inputs']} == expected
for name, row in inventory.items():
    relative = PurePosixPath(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    assert row['size'] > 0 and len(row['sha256']) == 64
for row in contract['compiled_changed_inputs']:
    data = (AREA / 'launcher-source' / row['path']).read_bytes()
    actual = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    assert actual == row['after'] == inventory[row['path']], row['path']
    assert row['before'] != row['after']
for row in contract['resource_mappings']:
    assert inventory[row['path']]['sha256'] == row['sha256']
assert len({row['name'] for row in contract['resource_mappings']}) == len(contract['resource_mappings'])
signed = (AREA / 'launcher-source/resources/ui-scroll-signedFriends.signed.json').read_bytes()
assert hashlib.sha256(signed).hexdigest() == contract['signed_manifest_sha256']
envelope = json.loads(signed)
assert set(envelope) == {'payload', 'signature'} and envelope['signature']
payload = json.loads(base64.b64decode(envelope['payload']))
assert payload['archive']['sha256'] == contract['runtime_archive']['sha256']
runtime = {row['path']: row for row in payload['files']}
assert len(runtime) == len(payload['files']) == contract['runtime_file_count'] == 2896
assert contract['preserved_runtime_file_count'] == 2894
assert contract['runtime_support_changes'] == 0
for row in sources['files']:
    if row['role'] != 'negative_regression_baseline':
        assert runtime[row['runtime_path']]['sha256'] == row['sha256']
cohort = (AREA / 'launcher-source/UIScrollRuntimeCohort.cs').read_text(encoding='utf-8-sig')
assert contract['runtime_archive']['sha256'] in cohort
assert contract['signed_manifest_sha256'] in cohort
assert runtime['tools/client_compatibility_profiles.json']['sha256'] in cohort
assert 'public const int Version = 123;' in (AREA / 'launcher-source/AutoUpdate.cs').read_text(encoding='utf-8-sig')
print(json.dumps({'ok': True, 'compiled_inventory': 146, 'archived_changed_inputs': 3,
                  'inherited_input_hash_references': 143, 'resource_mappings': len(contract['resource_mappings']),
                  'runtime_source_bindings': 12, 'public_release_or_upgrade_verified': False}))
