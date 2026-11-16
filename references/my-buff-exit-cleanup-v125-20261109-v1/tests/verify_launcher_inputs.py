"""Check archived private-build inputs; do not execute, rebuild or download a launcher.

Envelope bytes and decoded SHA bindings are checked, not independently verified RSA.
"""
from pathlib import Path, PurePosixPath
import base64
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
sha = lambda raw: hashlib.sha256(raw).hexdigest()
c = json.loads((ROOT / 'launcher-build-contract.json').read_bytes())
s = json.loads((ROOT / 'source-contract.json').read_bytes())
assert c['status'] == 'bound_private_build'
assert c['version'] == 125 and c['parent_version'] == 124
assert c['compiled_input_count'] == len(c['compiled_input_inventory']) == 146
assert c['inherited_unchanged_input_count'] == 143
assert len(c['compiled_changed_inputs']) == c['source_files_included'] == 3
expected_inputs = {'AutoUpdate.cs', 'UIScrollRuntimeCohort.cs',
                   'resources/ui-scroll-signedFriends.signed.json'}
assert {r['path'] for r in c['compiled_changed_inputs']} == expected_inputs
actual_inputs = {p.relative_to(ROOT / 'launcher-source').as_posix()
                 for p in (ROOT / 'launcher-source').rglob('*') if p.is_file()}
assert actual_inputs == expected_inputs
for name, row in c['compiled_input_inventory'].items():
    rel = PurePosixPath(name)
    assert not rel.is_absolute() and '..' not in rel.parts and ':' not in name
    assert row['size'] > 0 and len(row['sha256']) == 64
for row in c['compiled_changed_inputs']:
    raw = (ROOT / 'launcher-source' / row['path']).read_bytes()
    assert {'size': len(raw), 'sha256': sha(raw)} == row['after'] == c['compiled_input_inventory'][row['path']]
    assert row['before'] != row['after']
for row in c['resource_mappings']:
    assert c['compiled_input_inventory'][row['path']]['sha256'] == row['sha256']
assert len({r['name'] for r in c['resource_mappings']}) == len(c['resource_mappings']) == 101
raw = (ROOT / 'launcher-source/resources/ui-scroll-signedFriends.signed.json').read_bytes()
assert sha(raw) == c['signed_manifest_sha256']
envelope = json.loads(raw)
assert set(envelope) == {'payload', 'signature'} and envelope['signature']
payload = json.loads(base64.b64decode(envelope['payload'], validate=True))
assert payload['archive']['sha256'] == c['runtime_archive']['sha256']
assert payload['archive']['size'] == c['runtime_archive']['size']
runtime = {r['path']: r for r in payload['files']}
assert len(runtime) == len(payload['files']) == c['runtime_file_count'] == 2898
assert c['parent_runtime_file_count'] == 2896 and c['preserved_runtime_file_count'] == 2894
assert c['runtime_engine_changes'] == 0 and c['runtime_support_changes'] == 4
expected_support = {r['path'] for r in s['files']}
assert set(c['combined_runtime_delta']) == expected_support and len(expected_support) == 4
for row in s['files']:
    rel = row['path']
    assert runtime[rel]['sha256'] == row['sha256']
    assert runtime[rel]['size'] == row['size']
    assert c['combined_runtime_delta'][rel] == {'before': row['parent_sha256'], 'after': row['sha256']}
server = [{k: r[k] for k in ('path', 'size', 'sha256')} for r in payload['files'] if r['path'].startswith('els_server/')]
server.sort(key=lambda r: r['path'])
assert len(server) == c['server_file_count'] == 1448
assert sha(json.dumps(server, sort_keys=True, separators=(',', ':')).encode()) == c['unchanged_server_inventory_sha256']
assert c['server_parity_compared_to_parent'] is True
profile = json.loads((ROOT / 'source/tools/client_compatibility_profiles.json').read_bytes())
for item in profile['profiles']:
    assert len(item['artifacts']) == 62
    for rel in expected_support - {'tools/client_compatibility_profiles.json'}:
        assert item['artifacts'][rel] == runtime[rel]['sha256']
cohort = (ROOT / 'launcher-source/UIScrollRuntimeCohort.cs').read_text(encoding='utf-8-sig')
assert c['runtime_archive']['sha256'] in cohort and c['signed_manifest_sha256'] in cohort
assert runtime['tools/client_compatibility_profiles.json']['sha256'] in cohort
assert 'public const int Version = 125;' in (ROOT / 'launcher-source/AutoUpdate.cs').read_text(encoding='utf-8-sig')
assert c['original_EXE_KOM_changes'] == 0
print(json.dumps({'ok': True, 'compiled_inventory': 146, 'archived_changed_inputs': 3,
                  'inherited_input_hash_references': 143, 'resource_mappings': 101,
                  'runtime_files': 2898, 'preserved_runtime_files': 2894,
                  'support_delta_bindings': 4, 'unchanged_server_files': 1448,
                  'public_release_or_upgrade_verified': False,
                  'game_started': False, 'network_used': False}))
