"""Install a signed, accepted LOCAL runtime beside a clean Git checkout, without executing it."""
from pathlib import Path, PurePosixPath
from contextlib import contextmanager
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid

FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
OVERRIDES = {'tools/trace_dx11_login.js', 'tools/native_cache_sync.py', 'tools/launch_client.py', 'tools/launch_friends_client.py',
             'tools/client_compatibility_profiles.json', 'tools/local_fresh_state.py'}
ADDITIONS = {'tools/local_fresh_state.py','tools/native_wear_sync.py','tools/native_wear_sync.js','tools/world_event_iteration.py','tools/world_event_iteration.js'}
RESERVED = {'con', 'prn', 'aux', 'nul'} | {f'{p}{i}' for p in ('com', 'lpt') for i in range(1, 10)}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def hash_text(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def relative(value):
    need(isinstance(value, str) and 0 < len(value) <= 220, 'Invalid relative runtime path')
    need(not any(c in value for c in '\\:\x00\r\n*?"<>|'), 'Unsafe relative runtime path')
    path = PurePosixPath(value)
    need(not path.is_absolute() and str(path) == value, 'Noncanonical relative runtime path')
    need(all(p not in ('', '.', '..') and p == p.rstrip(' .') and
             p.split('.')[0].casefold() not in RESERVED for p in path.parts), 'Unsafe runtime leaf')
    return path


def no_links(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        need(not part.is_symlink() and not (hasattr(part, 'is_junction') and part.is_junction()),
             'Linked installation or source paths are refused')
    return path


def under(root, name):
    relative(name)
    root = no_links(root)
    path = root.joinpath(*PurePosixPath(name).parts)
    no_links(path)
    need(path.resolve().is_relative_to(root.resolve()), 'Runtime path escaped its root')
    return path


def read(path, maximum=4 * 1024 * 1024):
    path = no_links(path)
    need(path.is_file() and path.stat().st_size <= maximum, 'Missing or oversized JSON document')
    return json.loads(path.read_bytes())


def encoded(document):
    return (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def write_new(path, data):
    no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def atomic_new(path, data):
    """Publish a complete file atomically, refusing replacement on every platform."""
    no_links(path)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        write_new(temporary, data)
        # Same-directory NTFS/POSIX link creation is atomic and fails if path exists.
        os.link(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def progress(percent, message):
    print('ELS_BOOTSTRAP_PROGRESS:' + json.dumps({'percent': percent, 'message': message}, ensure_ascii=True), flush=True)


def rows(document):
    need(isinstance(document, dict) and isinstance(document.get('files'), list), 'Invalid verified runtime manifest')
    need(0 < len(document['files']) <= 4096, 'Runtime manifest file count exceeded')
    result, names, total = {}, set(), 0
    for row in document['files']:
        need(isinstance(row, dict), 'Invalid runtime entry')
        path = str(relative(row.get('path')))
        need(path.casefold() not in names and hash_text(row.get('sha256')) and
             type(row.get('size')) is int and 0 <= row['size'] <= 268435456, 'Invalid or duplicate runtime entry')
        names.add(path.casefold())
        total += row['size']
        need(total <= 2147483648, 'Runtime size budget exceeded')
        result[path] = {'path': path, 'size': row['size'], 'sha256': row['sha256']}
    return result


def source_rows_hash(file_rows):
    canonical = json.dumps([file_rows[path] for path in sorted(file_rows)], sort_keys=True,
                           separators=(',', ':'), ensure_ascii=False).encode('utf8')
    return hashlib.sha256(canonical).hexdigest()


def verify(root, row):
    path = under(root, row['path'])
    need(path.is_file() and path.stat().st_size == row['size'] and digest(path) == row['sha256'],
         'Runtime file failed SHA verification: ' + row['path'])


def git(repo, *arguments):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('GIT_'):
            del env[key]
    # Preserve the user's established text/eol normalization. Disabling their
    # Git configuration would falsely mark a clean CRLF checkout as modified.
    # No hooks or fsmonitor commands are allowed in these read-only operations.
    env.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    process = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.fsmonitor=false',
                              *arguments], cwd=repo, env=env, capture_output=True, timeout=120, creationflags=FLAGS)
    need(process.returncode == 0, 'Git repository verification failed')
    return process.stdout


def git_json(repo, commit, path):
    relative(path)
    raw = git(repo, 'cat-file', '-p', commit + ':' + path)
    need(len(raw) <= 8 * 1024 * 1024, 'Git metadata size exceeded')
    return json.loads(raw)


def git_unchanged(repo, commit):
    need(git(repo, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip() == commit,
         'Git HEAD changed during initialization')
    need(not git(repo, 'status', '--porcelain', '--untracked-files=all', '--ignore-submodules=all').strip(),
         'Git checkout has uncommitted or untracked changes')


def source_binding(repo, commit, runtime, manifest_rows, metadata):
    need(metadata.get('schema') == 1 and re.fullmatch('[a-z0-9][a-z0-9-]{0,95}', metadata.get('release', '')),
         'Invalid signed local source metadata')
    need(hash_text(metadata.get('source_formal_manifest_sha256')), 'Invalid source acceptance hash')
    selection = git_json(repo, commit, 'channels/current-engine.json')
    local = selection.get('accepted', {}).get('local', {})
    need(local.get('release') == metadata.get('source_release') and
         local.get('formal_manifest_sha256') == metadata['source_formal_manifest_sha256'] and
         selection.get('profile') == metadata.get('profile'), 'Git LOCAL acceptance differs from signed package')
    profile = git_json(repo, commit, selection['profile'])
    entries = profile.get('channels', {}).get('local', {}).get('files')
    need(isinstance(entries, list) and entries, 'Git LOCAL profile is incomplete')
    formal = rows({'files': entries})
    need(type(metadata.get('source_file_count')) is int and metadata['source_file_count'] == len(formal) and
         hash_text(metadata.get('source_files_sha256')) and
         source_rows_hash(formal) == metadata['source_files_sha256'],
         'Git LOCAL complete business index differs from the signed package')
    need('config/server.toml' in formal and
         hash_text(metadata.get('generated_config_source_sha256')) and
         metadata['generated_config_source_sha256'] == formal['config/server.toml']['sha256'] and
         'config/server.toml' not in manifest_rows,
         'Signed generated local configuration binding differs')
    original_entries = {entry['path']: entry for entry in entries}
    locked = rows(git_json(repo, commit, 'runtime-assets.lock.json'))
    overrides = {}
    for row in metadata.get('support_overrides', []):
        path = str(relative(row.get('path')))
        need(path in OVERRIDES and path not in overrides and path in formal and
             hash_text(row.get('source_sha256')) and hash_text(row.get('runtime_sha256')) and
             formal[path]['sha256'] == row['source_sha256'] and path in manifest_rows and
             manifest_rows[path]['sha256'] == row['runtime_sha256'], 'Invalid signed support override')
        overrides[path] = row
    additions = set()
    for row in metadata.get('support_additions', []):
        path = str(relative(row.get('path')))
        need(path in ADDITIONS and path not in additions and path not in formal and
             hash_text(row.get('runtime_sha256')) and path in manifest_rows and
             manifest_rows[path]['sha256'] == row['runtime_sha256'], 'Invalid signed support addition')
        additions.add(path)
    for index, (path, row) in enumerate(formal.items(), 1):
        entry = original_entries[path]
        need(('source' in entry) != ('asset' in entry), 'Ambiguous Git LOCAL source')
        if 'source' in entry:
            source = str(relative(entry['source']))
            raw = git(repo, 'cat-file', '-p', commit + ':' + source)
            need(len(raw) == row['size'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                 'Git LOCAL source differs: ' + path)
        else:
            need(entry['asset'] == path and path in locked and locked[path] == row,
                 'Git LOCAL asset is not locked: ' + path)
        if path != 'config/server.toml':
            need(path in manifest_rows, 'Signed LOCAL package omits accepted business file: ' + path)
            if path not in overrides:
                need(manifest_rows[path] == row, 'Signed LOCAL package differs from accepted business file: ' + path)
        if index % 64 == 0:
            progress(15 + 18 * index // len(formal), '正在逐项核对 Git 本地来源…')
    # A required helper must be signed and explicitly declared, never supplied by checkout.
    need('tools/local_fresh_state.py' in formal or 'tools/local_fresh_state.py' in additions,
         'Signed fresh-state helper was not declared')
    return formal, overrides, additions


def check_existing(workspace, metadata, signed_rows, generated):
    current = workspace / 'releases/local/current.json'
    pointer_bytes = no_links(current).read_bytes()
    pointer = read(current)
    need(pointer.get('channel') == 'local' and hash_text(pointer.get('manifest_sha256')),
         'Existing local pointer is invalid; no files were replaced')
    need(pointer.get('source_release') == metadata['source_release'] and
         pointer.get('source_formal_manifest_sha256') == metadata['source_formal_manifest_sha256'],
         'Existing local accepted source differs; update the unified launcher before upgrading')
    root = under(workspace, pointer.get('path'))
    need(root.parent == workspace / 'releases/local', 'Existing local pointer escapes releases')
    need(root.name == metadata['release'] and pointer.get('release') == metadata['release'],
         'Existing local runtime version differs; no files were replaced')
    need(digest(root / 'local-business-manifest.json') == pointer['manifest_sha256'],
         'Existing local business manifest differs; no files were replaced')
    business = rows(read(root / 'local-business-manifest.json'))
    bundle = rows(read(root / 'client-bundle-manifest.json'))
    need(set(bundle) == set(signed_rows) | {'config/server.toml', 'local-first-run.json'} and
         all(path in bundle and bundle[path] == row for path, row in signed_rows.items()),
         'Existing runtime differs from the signed local package')
    for name in ('config/server.toml', 'local-first-run.json'):
        need(no_links(root / name).read_bytes() == generated[name],
             'Existing local configuration or fresh marker differs; no files were replaced')
    need('els_server/application.py' in business and 'tools/launch_client.py' in bundle and
         'config/server.toml' in bundle and 'local-first-run.json' in bundle,
         'Existing first-install runtime is incomplete; no files were replaced')
    for row in bundle.values():
        verify(root, row)
    need(all(path in bundle and bundle[path] == row for path, row in business.items()),
         'Existing local business and runtime manifests differ')
    need(current.read_bytes() == pointer_bytes, 'Existing local pointer changed during verification')
    return {'ok': True, 'workspace': str(workspace), 'root': str(root),
            'release': pointer.get('release', root.name), 'reused': True}


@contextmanager
def installation_lock(workspace):
    path = workspace / '.first-local-install.lock'
    no_links(path)
    stream = path.open('a+b')
    try:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('Local initialization is already running; retry after it finishes') from error
        yield
    finally:
        # OS-held lock releases on close or process exit. Persistent zero-state lock
        # file avoids deleting another process's mutex between open and lock.
        stream.close()


def configuration(workspace):
    values = {'host': '127.0.0.1', 'port': 19400, 'profile': 'integrated_dx11', 'mode': 'local',
              'state_file': str(workspace / 'state/integrated.sqlite3'),
              'log_dir': str(workspace / 'logs/server'), 'attribute_enchant_enabled': True,
              'normal_equipment_moves_enabled': True, 'equipment_repair_enabled': True,
              'selected2026_pair_file': '../els_server/data/selected2026/local-pair.json'}
    return ('[server]\n' + ''.join(key + ' = ' + json.dumps(value, ensure_ascii=False) + '\n'
                                   for key, value in values.items())).encode('utf8')


def generated_documents(workspace, metadata, commit, manifest_rows, formal, additions):
    config = configuration(workspace)
    marker = encoded({'schema': 1, 'kind': 'els-local-fresh-state', 'workspace': str(workspace),
                      'release': metadata['release'], 'state_file': str(workspace / 'state/integrated.sqlite3'),
                      'config_sha256': hashlib.sha256(config).hexdigest()})
    documents = {'config/server.toml': config, 'local-first-run.json': marker}
    installed_rows = dict(manifest_rows)
    for name, data in documents.items():
        installed_rows[name] = {'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    business = encoded({'release': metadata['release'], 'channel': 'local',
                        'source_release': metadata['source_release'],
                        'source_formal_manifest_sha256': metadata['source_formal_manifest_sha256'],
                        'repository_commit': commit,
                        'files': [installed_rows[path] for path in sorted(set(formal) | additions)]})
    business_hash = hashlib.sha256(business).hexdigest()
    documents['local-business-manifest.json'] = business
    documents['client-bundle-manifest.json'] = encoded({'release': metadata['release'], 'channel': 'local',
                      'files': [installed_rows[path] for path in sorted(installed_rows)]})
    documents['release-snapshot.json'] = encoded({'release': metadata['release'], 'channel': 'local',
                      'status': 'initialized-from-signed-local-runtime', 'repository_commit': commit,
                      'local_business_manifest_sha256': business_hash, 'fresh_save_imported': False})
    pointer = {'ok': True, 'verified': True, 'release': metadata['release'], 'channel': 'local',
               'path': 'releases/local/' + metadata['release'], 'manifest_sha256': business_hash,
               'source_release': metadata['source_release'],
               'source_formal_manifest_sha256': metadata['source_formal_manifest_sha256'],
               'repository_commit': commit, 'first_initialization': True, 'player_database_imported': False}
    return documents, installed_rows, pointer


"""Bounded additions compiled into the bootstrap resource; not a separate component."""

MANAGED_KIND = 'unique-v42-managed-to-identity-v1'
MANAGED_OLD_ENVELOPE = 'c0fe16c35b05440258ed372ba2eb67da1419c2de62263e3b8c90aae4b7065371'
MANAGED_OLD_METADATA = '4688c349a9fb73a592c115ee610261cd9b2ba69cd5e9ccfafdd2b6050be575c1'
MANAGED_UPDATER = 'c976b8c28c85d54b128ac0943e1abf20969859c5139b7e3b5ece98bead049fc2'
MANAGED_OLD_FORMAL = 'd621337b400fc4dfe3a61bd32be2180bd98c55e4c8ab2beba3eae2e3e2b91b11'
MANAGED_NEW_FORMAL = '7c72970e3e5781c43a32d3f748d32c14fcedfe0b4f3f3fd660086a2cfcbf9f5e'
MANAGED_FIVE = {'els_server/storage/characters.py', 'els_server/storage/seal_quests.py',
                'els_server/storage/career_shop.py', 'els_server/protocol/local_messages.py',
                'els_server/protocol/dungeon_messages.py'}


# Exact third-cohort SOURCE descriptor; package identity excludes only metadata self-row.
STRUCTURE_SOURCE_RELEASE = 'local-native-server-structure-20261029-v1'
STRUCTURE_RUNTIME_RELEASE = 'local-git-first-run-server-structure-20261029-v1'
STRUCTURE_FORMAL = 'b014a2cfaab3968fb16055f85cbe35803b5cb5d1369382ee7ba5b6193dda43f2'
STRUCTURE_PROFILE = 'channels/server-structure-accepted-20261029-v1.json'
STRUCTURE_PROFILE_HASH = '05e234b9d1b055c1f991bea500d9d0f8ec15203a44cad33ccd6627de2f6b6a42'
STRUCTURE_SOURCE_ROWS = '6dc7ebde683c9ebea3d0327be7c7e46c3a1fd3843783869d05ddec4dc295f461'
STRUCTURE_RUNTIME_WITHOUT_METADATA = '850db3b453824c42f5dde271285783141a3b4dfaf2017d01aa3ee5bcb5cd3b38'
STRUCTURE_POLICY_KIND = 'exact-v42-or-identity-to-server-structure-v1'
STRUCTURE_PREDECESSORS = [{'name': 'v42', 'key': ('local-git-first-run-20261029-v1', 'local-native-shop-flow-20261029-v1', 'd621337b400fc4dfe3a61bd32be2180bd98c55e4c8ab2beba3eae2e3e2b91b11'), 'envelope': 'c0fe16c35b05440258ed372ba2eb67da1419c2de62263e3b8c90aae4b7065371', 'metadata': '4688c349a9fb73a592c115ee610261cd9b2ba69cd5e9ccfafdd2b6050be575c1', 'archive': '70e06dca0f929d0f2bc053a5cb226b960bf7026c13ae10dda503f96f485aeec4', 'runtime_rows': '1d8c54487337d12b72bd2f8ae58b8d2e211cae83ab939a61c4f1e9f9c453afbe', 'formal_rows': '7900ad4eef4985b6b953b00e880f8b303224e0bb97debd59e178057301de3cdb'}, {'name': 'identity', 'key': ('local-git-first-run-identity-20261029-v1', 'local-native-unit-account-identity-20261029-v1', '7c72970e3e5781c43a32d3f748d32c14fcedfe0b4f3f3fd660086a2cfcbf9f5e'), 'envelope': 'ed47a5df4fd5d47bacf297226cce4783866ded16d88074b14d277e9bebeffa04', 'metadata': '0a2e4071eb897b8e0b6b210152d305b28bbe571366b95b86f8ed0b5dec54432c', 'archive': 'c2479938972ae6f9c6f3747d2348f28473dbaa2635ee93e16c1b9239e309f86e', 'runtime_rows': '6d87d9dcac786bc9644b686fe6cf1d41f0c55ea2c8d1c0bd2d98f354340c7d35', 'formal_rows': 'b36e18da6a4a3729d8a3b8dd20f4a486906cbd88e62158c2a97d893b2cbe49b8'}]
STRUCTURE_OVERRIDES = [{'path': 'tools/launch_client.py', 'source_sha256': '74f5c5406c93b526e1bb34cac36c5eb4ef8eeca4fbc3292d05c5de8f18f08142', 'runtime_sha256': '9cb6fd2b579b11c90ec2ccc31babd3c383e9b8bbd43ccfed330cdf4aa689e6f8'}, {'path': 'tools/client_compatibility_profiles.json', 'source_sha256': '9f6a0cc4ee8c3f2f293cc2b19c94610f31bc029e0aeb9ddb7c278dc6f478aff0', 'runtime_sha256': '04166e975104b9d25e7bf224eeb1a2f34501689cc33cb76ee457c0b4797906e1'}]
STRUCTURE_ADDITIONS = [{'path': 'tools/local_fresh_state.py', 'runtime_sha256': '9bed6a12b3adeeb63f49d60f81bc8f89a64c1e676726ee09a7d627382efe9d56'}]
STRUCTURE_CONFIG = '4e14201a91e69df87af8bf5aac226f303f027fde76b98e2967b85c442c2e8124'


def structure_target(metadata):
    return (metadata.get('release'), metadata.get('source_release'), metadata.get('source_formal_manifest_sha256')) == (STRUCTURE_RUNTIME_RELEASE, STRUCTURE_SOURCE_RELEASE, STRUCTURE_FORMAL)


def structure_policy(metadata, new_rows):
    import base64
    need(structure_target(metadata), 'Unknown STRUCTURE managed target')
    need(metadata.get('profile') == STRUCTURE_PROFILE and type(metadata.get('source_file_count')) is int and
         metadata['source_file_count'] == 1332 and metadata.get('source_files_sha256') == STRUCTURE_SOURCE_ROWS,
         'STRUCTURE complete accepted business identity differs')
    need(metadata.get('support_overrides') == STRUCTURE_OVERRIDES and metadata.get('support_additions') == STRUCTURE_ADDITIONS and
         metadata.get('generated_config_source_sha256') == STRUCTURE_CONFIG, 'STRUCTURE signed support/config differs')
    need(len(new_rows) == 1786 and 'local-bootstrap-source.json' in new_rows and
         source_rows_hash({k:v for k,v in new_rows.items() if k != 'local-bootstrap-source.json'}) == STRUCTURE_RUNTIME_WITHOUT_METADATA,
         'STRUCTURE exact complete runtime membership differs')
    p = metadata.get('upgrade_from')
    need(isinstance(p, dict) and type(p.get('schema')) is int and p['schema'] == 1 and
         p.get('kind') == STRUCTURE_POLICY_KIND and
         (p.get('to_runtime_release'), p.get('to_source_release'), p.get('to_source_formal_manifest_sha256')) ==
         (STRUCTURE_RUNTIME_RELEASE, STRUCTURE_SOURCE_RELEASE, STRUCTURE_FORMAL), 'STRUCTURE signed predecessor policy differs')
    entries = p.get('predecessors')
    need(isinstance(entries, list) and len(entries) == 2, 'STRUCTURE requires exactly two pinned predecessor definitions')
    contracts = {}
    for entry, fixed in zip(entries, STRUCTURE_PREDECESSORS):
        key = tuple(entry.get(k) for k in ('from_runtime_release','from_source_release','from_source_formal_manifest_sha256'))
        need(entry.get('name') == fixed['name'] and key == tuple(fixed['key']) and key not in contracts,
             'Unknown or duplicate STRUCTURE predecessor')
        eb = base64.b64decode(entry['old_signed_envelope_base64'], validate=True)
        need(len(eb) < 1048576 and hashlib.sha256(eb).hexdigest() == entry.get('old_signed_envelope_sha256') == fixed['envelope'],
             'STRUCTURE original signed envelope identity differs')
        signed = json.loads(base64.b64decode(json.loads(eb)['payload'], validate=True))
        old_rows = rows(signed)
        need(len(old_rows) == 1779 and source_rows_hash(old_rows) == fixed['runtime_rows'] and
             signed['archive']['sha256'] == fixed['archive'], 'STRUCTURE original full signed membership differs')
        mb = base64.b64decode(entry['old_metadata_base64'], validate=True)
        need(len(mb) < 1048576 and hashlib.sha256(mb).hexdigest() == entry.get('old_metadata_sha256') ==
             fixed['metadata'] == old_rows['local-bootstrap-source.json']['sha256'], 'STRUCTURE original metadata differs')
        old_meta = json.loads(mb)
        need((old_meta['release'], old_meta['source_release'], old_meta['source_formal_manifest_sha256']) == key,
             'STRUCTURE original accepted metadata target differs')
        old_formal = rows({'files':entry['old_formal_rows']})
        need(len(old_formal) == old_meta['source_file_count'] == 1325 and source_rows_hash(old_formal) ==
             entry.get('old_formal_rows_sha256') == fixed['formal_rows'] == old_meta['source_files_sha256'],
             'STRUCTURE original complete business source differs')
        need(entry.get('updater_sha256') == MANAGED_UPDATER, 'STRUCTURE exact updater differs')
        contracts[key] = dict(policy=entry, old_rows=old_rows, old_meta=old_meta, old_formal=old_formal,
                             policy_sha256=hashlib.sha256(encoded(dict(target=p, selected=entry['name']))).hexdigest())
    return dict(structure_contracts=contracts)


def structure_select(contract, pointer):
    if 'structure_contracts' not in contract:
        return contract
    key = tuple(pointer.get(k) for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key in contract['structure_contracts'], 'Existing source is not an exact STRUCTURE predecessor')
    return contract['structure_contracts'][key]


def structure_journal_contract(workspace, u, contract, path):
    if 'structure_contracts' not in contract:
        return contract
    path = no_links(Path(path))
    need(path.is_absolute() and path == path.resolve() and path.is_relative_to(workspace / 'state/local-updater') and
         path.name == 'journal.json', 'STRUCTURE recovery journal escaped its canonical root')
    journal = u.read(path)
    return structure_select(contract, journal['parent'])



# SOURCE ONLY: every new descriptor value is pending final reviewed C3.
REPAIR_SOURCE_RELEASE = 'local-accessory-identification-groups-20261030-v1'
REPAIR_RUNTIME_RELEASE = 'local-git-first-run-login-reconnect-20261031-v1'
REPAIR_FORMAL = '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'
REPAIR_PROFILE = 'channels/accessory-identification-accepted-20261031-v1.json'
REPAIR_PROFILE_HASH = '3f7002d2e2b5601d9ec2225bda47fc80b75646bea2cd22d29e8fcdcb3e9aab32'
REPAIR_SOURCE_ROWS = 'd7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999'
REPAIR_SOURCE_COUNT = 1342
REPAIR_RUNTIME_COUNT = 1800
REPAIR_RUNTIME_WITHOUT_METADATA = '3f834e99a05461af99137c56a8a51af5e15b1018fc1b6c166e203c0128ed6ff2'
REPAIR_SOURCE_SET = '250a0581df1ca0cb945786c4cfb699b419997b66d24141fa9d02eb444d2ee2f8'
REPAIR_OVERRIDES = [{'path': 'tools/launch_client.py', 'source_sha256': '74f5c5406c93b526e1bb34cac36c5eb4ef8eeca4fbc3292d05c5de8f18f08142', 'runtime_sha256': '9cb6fd2b579b11c90ec2ccc31babd3c383e9b8bbd43ccfed330cdf4aa689e6f8'}, {'path': 'tools/client_compatibility_profiles.json', 'source_sha256': 'f1661177edd96176b2bd0b7e869215ab27e0337e186f77c1bd026248b2ae4a9e', 'runtime_sha256': '63d7df5e475f1f2c34ee72d5d86c0ff4df331021a71277d67957be8e0c3db6c0'}, {'path': 'tools/native_cache_sync.py', 'source_sha256': '225d321ef32563a5736513dd4030118aa669ac2e49cf8a3f7ac7344f4ef21856', 'runtime_sha256': '4674857aaca22f893a3b54ca69d0beb115011025d2146c851a4528186109df17'}, {'path': 'tools/trace_dx11_login.js', 'source_sha256': 'c837f547abf0e34a2768256f503af5dc04f3caccc01e5f88dc7675bf009c30ed', 'runtime_sha256': '640a6daeffd8e43382a1e0e5de9b3aa4a8a75716f265d7d372f2344179f75bb3'}]
REPAIR_ADDITIONS = [{'path': 'tools/local_fresh_state.py', 'runtime_sha256': '9bed6a12b3adeeb63f49d60f81bc8f89a64c1e676726ee09a7d627382efe9d56'}, {'path': 'tools/native_wear_sync.py', 'runtime_sha256': '0c448f6b5aa891e633b90ef5d221c56af5d422721dece5a7c8209819aca937f7'}, {'path': 'tools/native_wear_sync.js', 'runtime_sha256': '8655b2d8ced704417319c535ed08b4be6c3b56ebe55eedec7fe6cedf3100e604'}, {'path': 'tools/world_event_iteration.py', 'runtime_sha256': '01d80c31b6ac048a9c0383ca82a4ed2661bbc1ee1afb59932861707409f26d6b'}, {'path': 'tools/world_event_iteration.js', 'runtime_sha256': '06fbd593215c6a03774d9fbcc594754b7edee5f083c015331e39bb867db69ed0'}]
REPAIR_CONFIG = '4e14201a91e69df87af8bf5aac226f303f027fde76b98e2967b85c442c2e8124'
REPAIR_POLICY_KIND = 'exact-v51-transitive-to-login-reconnect-v1'
REPAIR_STRUCTURE_ENVELOPE = 'e11a4123f68270db611b7b5fda991c8630b9650a6de2a842d3c447b8d762cfc0'
REPAIR_STRUCTURE_METADATA = '8acdfd6bbfcdc02af18ee29e3e8b1fbffcc9b48370de5d83806fb7424a6e0c27'
REPAIR_STRUCTURE_METADATA_LENGTH = 2306378

def repair_require_bindings():
    need(all(isinstance(v,str) and v for v in (REPAIR_SOURCE_RELEASE,REPAIR_RUNTIME_RELEASE,REPAIR_PROFILE)) and
         all(hash_text(v) for v in (REPAIR_FORMAL,REPAIR_PROFILE_HASH,REPAIR_SOURCE_ROWS,REPAIR_RUNTIME_WITHOUT_METADATA,REPAIR_SOURCE_SET,REPAIR_CONFIG)) and
         type(REPAIR_SOURCE_COUNT)is int and type(REPAIR_RUNTIME_COUNT)is int and
         type(REPAIR_OVERRIDES)is list and type(REPAIR_ADDITIONS)is list,
         'Final C3 repair source/descriptor bindings pending; stop before Prepare/initialize')

def repair_target(metadata):
    return hash_text(REPAIR_FORMAL) and (metadata.get('release'),metadata.get('source_release'),metadata.get('source_formal_manifest_sha256')) == (REPAIR_RUNTIME_RELEASE,REPAIR_SOURCE_RELEASE,REPAIR_FORMAL)

def repair_v44_predecessors(entry):
    # One public V44 object contains the original two fixed predecessors. Never
    # duplicate their megabytes or broaden the old structure policy limit.
    import base64
    need(type(entry)is dict and set(entry)=={'name','old_signed_envelope_base64','old_signed_envelope_sha256','old_metadata_base64','old_metadata_sha256','old_formal_rows'}, 'Exact V44 predecessor fields required')
    need(entry['name']=='structure', 'Exact V44 predecessor name required')
    eb=base64.b64decode(entry['old_signed_envelope_base64'],validate=True)
    need(len(eb)<1048576 and hashlib.sha256(eb).hexdigest()==entry['old_signed_envelope_sha256']==REPAIR_STRUCTURE_ENVELOPE, 'Exact old V44 signed envelope differs')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1786 and signed['archive']['sha256']=='d4481559a4c0ffff4bc4b94855d7ae5dcbfc67f5295a1f7428da69de9cce02d7', 'Exact old V44 complete runtime differs')
    mb=base64.b64decode(entry['old_metadata_base64'],validate=True)
    need(len(mb)==REPAIR_STRUCTURE_METADATA_LENGTH and hashlib.sha256(mb).hexdigest()==entry['old_metadata_sha256']==REPAIR_STRUCTURE_METADATA==old_rows['local-bootstrap-source.json']['sha256'] and old_rows['local-bootstrap-source.json']['size']==len(mb), 'Exact old V44 metadata bytes differ')
    old_meta=json.loads(mb);old_formal=rows({'files':entry['old_formal_rows']})
    need(len(old_formal)==old_meta['source_file_count']==1332 and source_rows_hash(old_formal)==old_meta['source_files_sha256']==STRUCTURE_SOURCE_ROWS, 'Exact old V44 formal rows differ')
    inherited=structure_policy(old_meta,old_rows)['structure_contracts']
    need(len(inherited)==2, 'Exact two validated V44 predecessors required')
    result=dict(inherited);key=(STRUCTURE_RUNTIME_RELEASE,STRUCTURE_SOURCE_RELEASE,STRUCTURE_FORMAL)
    need(key not in result and (old_meta['release'],old_meta['source_release'],old_meta['source_formal_manifest_sha256'])==key, 'Exact old V44 source tuple differs')
    result[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    need(len(result)==3, 'Repair requires three distinct exact predecessors')
    return result


def cache_v45_predecessors(entry):
    import base64,zlib
    need(type(entry)is dict and set(entry)=={'encoding','data'} and entry['encoding']=='zlib-base64-v45-public-v1', 'Exact V45 predecessor container required')
    need(type(entry['data'])is str and len(entry['data'])<=4*1024*1024, 'Encoded V45 predecessor too large')
    compressed=base64.b64decode(entry['data'],validate=True)
    need(len(compressed)<=3*1024*1024, 'Compressed predecessor too large')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail, 'Truncated, trailing or oversized predecessor')
    d=json.loads(raw)
    need(type(d)is dict and set(d)=={'envelope_base64','metadata_base64','formal_rows'}, 'Unexpected predecessor document fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True)
    need(len(eb)<1048576 and hashlib.sha256(eb).hexdigest()=='5004c9eccdbe717c41581c42c0b56658bb23009fdeebda21b7e5050380a81af8','V45 signed envelope changed')
    env=json.loads(eb);signed=json.loads(base64.b64decode(env['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1794 and signed['archive']['sha256']=='0e3efdb292016dee1904d86c463ac35165496ec9524cc5d7ea89a3c7325fb9b5','V45 archive identity changed')
    mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(len(mb)==3789766 and hashlib.sha256(mb).hexdigest()=='2adb90a9bd462e004fa7b8861fa3f9af91161ba383f778f85843f915a2010daa','V45 original metadata changed')
    need(old_rows['local-bootstrap-source.json']['sha256']==hashlib.sha256(mb).hexdigest() and old_rows['local-bootstrap-source.json']['size']==len(mb),'V45 signed metadata membership differs')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    key=('local-git-first-run-shared-repair-20261030-v1','local-native-shared-repair-20261030-v1','2291d8c2e24f72209e802de082fda701f623fc87609e201206136f5862ff9fd5')
    need(tuple(old_meta[k] for k in ('release','source_release','source_formal_manifest_sha256'))==key,'V45 source tuple changed')
    need(len(old_formal)==1340 and source_rows_hash(old_formal)==old_meta['source_files_sha256']=='3e8430e117e2cc370801c06a7d62f54c10ee3fa4d4357ebccfc4f40231701947','V45 formal rows changed')
    contracts=repair_v44_predecessors(old_meta['upgrade_from']['structure_predecessor'])
    need(len(contracts)==3 and key not in contracts,'V45 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def owned_v46_predecessors(entry):
    import base64,zlib
    need(type(entry)is dict and set(entry)=={'encoding','data'} and entry['encoding']=='zlib-base64-v46-public-v1', 'Exact V46 predecessor container required')
    need(type(entry['data'])is str and len(entry['data'])<=4*1024*1024, 'Encoded V46 predecessor too large')
    compressed=base64.b64decode(entry['data'],validate=True)
    need(len(compressed)<=3*1024*1024, 'Compressed predecessor too large')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail, 'Truncated, trailing or oversized predecessor')
    d=json.loads(raw)
    need(type(d)is dict and set(d)=={'envelope_base64','metadata_base64','formal_rows'}, 'Unexpected predecessor document fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True)
    need(len(eb)<1048576 and hashlib.sha256(eb).hexdigest()=='bd6ad8dd2301b4c4d8ec24209889c0c32d0a7ebb23bc0385824e7f4ce575defa','V46 signed envelope changed')
    env=json.loads(eb);signed=json.loads(base64.b64decode(env['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1794 and signed['archive']['sha256']=='ee68800402e6dc7ef6e8317d07595ffd4b220034c1477a0f122faf311e9d9d78','V46 archive identity changed')
    mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(len(mb)==2868747 and hashlib.sha256(mb).hexdigest()=='8df4c6fe66868123516414a9351026c1d5dbec84a42fd26421ea735cd81a349c','V46 original metadata changed')
    need(old_rows['local-bootstrap-source.json']['sha256']==hashlib.sha256(mb).hexdigest() and old_rows['local-bootstrap-source.json']['size']==len(mb),'V46 signed metadata membership differs')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    key=('local-git-first-run-cache-exact41400-20261030-v1','local-cache-exact41400-20261030-v1','7dd7cab0d08b85c9803e0c96d92109d4d5c2d22d729e47c0104d7f8e40d93b35')
    need(tuple(old_meta[k] for k in ('release','source_release','source_formal_manifest_sha256'))==key,'V46 source tuple changed')
    need(len(old_formal)==1340 and source_rows_hash(old_formal)==old_meta['source_files_sha256']=='bd405d403efec936c3a78a8a1a6eefb1a48debdbcd2f3c6b6e44b7c804430f6e','V46 formal rows changed')
    contracts=cache_v45_predecessors(old_meta['upgrade_from']['v45_predecessor'])
    need(len(contracts)==4 and key not in contracts,'V46 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

ACCESSORY_V47_PARTS = [('accessory-predecessor-a.txt', '1bb578d4f823db385caa49f7657feb9893c12153ec5dc557eba1ecc8c2f9fa62'), ('accessory-predecessor-b.txt', 'a178e771ba22bac3a2757cae88e65a8f580f9955f5f3d2ea76161a11260ec679')]

def accessory_v47_predecessors(entry):
    import base64,zlib
    need(type(entry)is dict and set(entry)=={'encoding','sha256'} and entry['encoding']=='embedded-zlib-base64-v47-public-v1', 'Exact V47 predecessor container required')
    need(entry['sha256']=='023f6ee8f9375eee96e5e975d3197c028cc6e47b6d3cfafdf4e297b7afbaf4c1', 'Embedded predecessor identity')
    pieces=[]
    for leaf,expected in ACCESSORY_V47_PARTS:
        raw=no_links(Path(__file__).resolve().with_name(leaf)).read_bytes()
        need(len(raw)<=3*1024*1024 and hashlib.sha256(raw).hexdigest()==expected,'Embedded predecessor part changed')
        pieces.append(raw.decode('ascii'))
    compressed=base64.b64decode(''.join(pieces),validate=True)
    need(hashlib.sha256(compressed).hexdigest()==entry['sha256'],'Embedded predecessor digest')
    need(len(compressed)<=4*1024*1024, 'Compressed predecessor too large')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail, 'Truncated, trailing or oversized predecessor')
    d=json.loads(raw)
    need(type(d)is dict and set(d)=={'envelope_base64','metadata_base64','formal_rows'}, 'Unexpected predecessor document fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True)
    need(len(eb)<1048576 and hashlib.sha256(eb).hexdigest()=='cedeb7b01f9f1d3da10e968d827897aba412f6146b95e7250c5bfbb028cbc933','V47 signed envelope changed')
    env=json.loads(eb);signed=json.loads(base64.b64decode(env['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1795 and signed['archive']['sha256']=='fdfec5119af224754a2155c739a0d0e4163a1706e31903f2e9e65b6fb678d27c','V47 archive identity changed')
    mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(len(mb)==3834763 and hashlib.sha256(mb).hexdigest()=='1088d1049ade31b3d3fd1a515718a6d9875a3e26951b14bff05b96dad6531edf','V47 original metadata changed')
    need(old_rows['local-bootstrap-source.json']['sha256']==hashlib.sha256(mb).hexdigest() and old_rows['local-bootstrap-source.json']['size']==len(mb),'V47 signed metadata membership differs')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    key=('local-git-first-run-owned-stones-nine-leaf-20261030-v1', 'local-owned-stones-nine-leaf-20261030-v1', '965f336f1f5f940746eedf51c1c94f57c60abbdffc50e78c025e1da3d4ff3558')
    need(tuple(old_meta[k] for k in ('release','source_release','source_formal_manifest_sha256'))==key,'V47 source tuple changed')
    need(len(old_formal)==1341 and source_rows_hash(old_formal)==old_meta['source_files_sha256']=='dbfc5f586a692e6acb240a1dd27ff29995893210550f5ecd8e7d3750a6dd0a41','V47 formal rows changed')
    contracts=owned_v46_predecessors(old_meta['upgrade_from']['v46_predecessor'])
    need(len(contracts)==5 and key not in contracts,'V47 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def wear_v48_predecessors(entry):
    import base64,zlib
    need(entry=={'encoding': 'embedded-zlib-base64-v48-public-v1', 'sha256': 'c76bbbef58618ce7b4aff307843b1906b5e7ce8e32a100bad2fc83894fc01917'},'Exact V48 predecessor descriptor required')
    raw=no_links(Path(__file__).resolve().with_name('wear-predecessor.txt')).read_bytes()
    need(len(raw)==309824 and hashlib.sha256(raw).hexdigest()=='68b74b889731569534bf952510dd61402669aa605bc878e9fa4e2aa80184fe7c','V48 predecessor resource changed')
    compressed=base64.b64decode(raw,validate=True)
    need(hashlib.sha256(compressed).hexdigest()=='c76bbbef58618ce7b4aff307843b1906b5e7ce8e32a100bad2fc83894fc01917','V48 compressed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V48 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V48 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()=='1719deff1d845338fc8160eaad1f01805552144d4779977e29099c9cca4c3cf7' and hashlib.sha256(mb).hexdigest()=='836dd3b532e63cf22f95771ec234f5de3696e004655b9cdf8ceb5a080698e4da','V48 predecessor identities')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1796 and signed['archive']['sha256']=='201c28a1efb7a5c64a6f9f5998a5af770aced95ffebfefc12614c1eaef92c444','V48 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']=='d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999','V48 source rows changed')
    key=tuple(old_meta[k]for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key==('local-git-first-run-accessory-identification-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'),'V48 source identity changed')
    contracts=accessory_v47_predecessors(old_meta['upgrade_from']['v47_predecessor'])
    need(len(contracts)==6 and key not in contracts,'V48 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def world_v50_predecessors(entry):
    import base64,zlib
    need(entry=={'encoding': 'embedded-zlib-base64-v50-public-v1', 'sha256': 'fa12cde321783cacd6b22bec2ddd556ce498f223399c50a53c63c138ecc52c16'},'Exact V50 predecessor descriptor required')
    raw=no_links(Path(__file__).resolve().with_name('world-predecessor.txt')).read_bytes()
    need(len(raw)==310316 and hashlib.sha256(raw).hexdigest()=='fac2c5f0afdf3cee8593a03af0ce919a754bbef27d0d3b2807720d785faad4fd','V50 predecessor resource changed')
    compressed=base64.b64decode(raw,validate=True)
    need(hashlib.sha256(compressed).hexdigest()=='fa12cde321783cacd6b22bec2ddd556ce498f223399c50a53c63c138ecc52c16','V50 compressed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V50 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V50 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()=='a447d5f623f75850deeee35642bccbd0223eac3c43fad0cc66c50f55d539a323' and hashlib.sha256(mb).hexdigest()=='c1629eaf234f82a5c1b308b5277054a6b9530e55ceb54e4f6a3a9a666fa6e3f7','V50 predecessor identities')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1798 and signed['archive']['sha256']=='458145b1f399cb10095c15769a6057f81a3570dc4f29e9878d7582f29b34a656','V50 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']=='d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999','V50 source rows changed')
    key=tuple(old_meta[k]for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key==('local-git-first-run-wear-wait-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'),'V50 source identity changed')
    contracts=wear_v48_predecessors(old_meta['upgrade_from']['v48_predecessor'])
    need(len(contracts)==7 and key not in contracts,'V50 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def login_v51_predecessors(entry):
    import base64,zlib
    need(entry=={'encoding': 'embedded-zlib-base64-v51-public-v1', 'sha256': 'caf5756786c924dffe4bba1f7adc2bc69644ab1d11c864e3d1d5829be076f428'},'Exact V51 predecessor descriptor required')
    raw=no_links(Path(__file__).resolve().with_name('login-predecessor.txt')).read_bytes()
    need(len(raw)==310896 and hashlib.sha256(raw).hexdigest()=='354920a6e9bd854d654ba93bb1ff61032bc828979ef0f256b6c5e510dd5c8e20','V51 predecessor resource changed')
    compressed=base64.b64decode(raw,validate=True)
    need(hashlib.sha256(compressed).hexdigest()=='caf5756786c924dffe4bba1f7adc2bc69644ab1d11c864e3d1d5829be076f428','V51 compressed predecessor changed')
    dec=zlib.decompressobj();raw=dec.decompress(compressed,8*1024*1024+1)
    need(len(raw)<=8*1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'V51 predecessor bound')
    d=json.loads(raw);need(set(d)=={'envelope_base64','metadata_base64','formal_rows'},'V51 predecessor fields')
    eb=base64.b64decode(d['envelope_base64'],validate=True);mb=base64.b64decode(d['metadata_base64'],validate=True)
    need(hashlib.sha256(eb).hexdigest()=='cd9c20dd6736c5efc50aa4a2090fb15c21db2a5484b02d68b3a8ff402a515be7' and hashlib.sha256(mb).hexdigest()=='e4d97944fd696c01534c4c656821d13ed7061c860807d9949aa03c4b2321591d','V51 predecessor identities')
    signed=json.loads(base64.b64decode(json.loads(eb)['payload'],validate=True));old_rows=rows(signed)
    need(len(old_rows)==1800 and signed['archive']['sha256']=='767a908a9ca8e18a74d3153056b283226d3dbab24edd5e113a715fb724e06c2d','V51 signed runtime changed')
    old_meta=json.loads(mb);old_formal=rows({'files':d['formal_rows']})
    need(source_rows_hash(old_formal)==old_meta['source_files_sha256']=='d7bb41258213811e00279f207114b12c672ac7de8a19aa29dc515df91ccb0999','V51 source rows changed')
    key=tuple(old_meta[k]for k in ('release','source_release','source_formal_manifest_sha256'))
    need(key==('local-git-first-run-world-event-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69'),'V51 source identity changed')
    contracts=world_v50_predecessors(old_meta['upgrade_from']['v50_predecessor'])
    need(len(contracts)==8 and key not in contracts,'V51 transitive predecessors changed')
    contracts[key]=dict(policy=entry,old_rows=old_rows,old_meta=old_meta,old_formal=old_formal,policy_sha256=hashlib.sha256(encoded(entry)).hexdigest())
    return contracts

def repair_policy(metadata,new_rows):
    repair_require_bindings()
    need(repair_target(metadata) and metadata.get('profile')==REPAIR_PROFILE and metadata.get('source_files_sha256')==REPAIR_SOURCE_ROWS and type(metadata.get('source_file_count'))is int and metadata['source_file_count']==REPAIR_SOURCE_COUNT, 'Exact repair source descriptor differs')
    need(metadata.get('support_overrides')==REPAIR_OVERRIDES and metadata.get('support_additions')==REPAIR_ADDITIONS and metadata.get('generated_config_source_sha256')==REPAIR_CONFIG, 'Exact repair support/config differs')
    need(len(new_rows)==REPAIR_RUNTIME_COUNT and 'local-bootstrap-source.json'in new_rows and source_rows_hash({k:v for k,v in new_rows.items()if k!='local-bootstrap-source.json'})==REPAIR_RUNTIME_WITHOUT_METADATA, 'Exact repair complete runtime differs')
    need(len(encoded(metadata))<=4*1024*1024, 'Repair metadata exceeds original total4MiB limit')
    p=metadata.get('upgrade_from')
    need(type(p)is dict and set(p)=={'schema','kind','to_runtime_release','to_source_release','to_source_formal_manifest_sha256','v51_predecessor'} and type(p['schema'])is int and p['schema']==1 and p['kind']==REPAIR_POLICY_KIND, 'Exact transitive repair policy required')
    need((p['to_runtime_release'],p['to_source_release'],p['to_source_formal_manifest_sha256'])==(REPAIR_RUNTIME_RELEASE,REPAIR_SOURCE_RELEASE,REPAIR_FORMAL), 'Repair policy target differs')
    contracts=login_v51_predecessors(p['v51_predecessor'])
    for key,contract in contracts.items():contract['policy_sha256']=hashlib.sha256(encoded(dict(target=p,selected=list(key)))).hexdigest()
    return dict(structure_contracts=contracts)

def managed_policy(metadata, new_rows):
    if repair_target(metadata):
        return repair_policy(metadata,new_rows)
    if structure_target(metadata):
        return structure_policy(metadata, new_rows)
    import base64
    p = metadata.get('upgrade_from')
    if p is None:
        return None
    need(isinstance(p, dict) and type(p.get('schema')) is int and p['schema'] == 1 and p.get('kind') == MANAGED_KIND,
         'Unrecognized managed predecessor policy')
    need((p.get('from_runtime_release'), p.get('from_source_release'), p.get('from_source_formal_manifest_sha256')) ==
         ('local-git-first-run-20261029-v1', 'local-native-shop-flow-20261029-v1', MANAGED_OLD_FORMAL),
         'Only the exact accepted V42 predecessor is eligible')
    need((metadata.get('release'), metadata.get('source_release'), metadata.get('source_formal_manifest_sha256')) ==
         ('local-git-first-run-identity-20261029-v1', 'local-native-unit-account-identity-20261029-v1', MANAGED_NEW_FORMAL),
         'Managed upgrade target is not the accepted identity source')
    need((p.get('to_runtime_release'), p.get('to_source_release'), p.get('to_source_formal_manifest_sha256')) ==
         (metadata['release'], metadata['source_release'], metadata['source_formal_manifest_sha256']),
         'Managed predecessor policy target differs')
    raw = base64.b64decode(p['old_signed_envelope_base64'], validate=True)
    need(len(raw) < 1048576 and hashlib.sha256(raw).hexdigest() == p['old_signed_envelope_sha256'] == MANAGED_OLD_ENVELOPE,
         'Original V42 signed envelope identity differs')
    old_signed = json.loads(base64.b64decode(json.loads(raw)['payload'], validate=True))
    old_rows = rows(old_signed)
    need(len(old_rows) == 1779 and old_signed['archive']['sha256'] == '70e06dca0f929d0f2bc053a5cb226b960bf7026c13ae10dda503f96f485aeec4',
         'Original signed V42 full membership differs')
    raw = base64.b64decode(p['old_metadata_base64'], validate=True)
    need(hashlib.sha256(raw).hexdigest() == p['old_metadata_sha256'] == MANAGED_OLD_METADATA == old_rows['local-bootstrap-source.json']['sha256'],
         'Original V42 metadata identity differs')
    old_meta = json.loads(raw)
    need((old_meta['release'], old_meta['source_release'], old_meta['source_formal_manifest_sha256']) ==
         (p['from_runtime_release'], p['from_source_release'], p['from_source_formal_manifest_sha256']),
         'Original V42 metadata source differs')
    old_formal = rows({'files': p['old_formal_rows']})
    need(len(old_formal) == old_meta['source_file_count'] == 1325 and
         source_rows_hash(old_formal) == p['old_formal_rows_sha256'] == old_meta['source_files_sha256'],
         'Original V42 complete business index differs')
    need(set(new_rows) == set(old_rows) and len(new_rows) == 1779 and
         {n for n in old_rows if old_rows[n] != new_rows[n]} == MANAGED_FIVE | {'local-bootstrap-source.json'},
         'Managed signed package is not the exact six-row identity delta')
    need(metadata.get('support_overrides') == old_meta['support_overrides'] and
         metadata.get('support_additions') == old_meta['support_additions'] and
         metadata.get('generated_config_source_sha256') == old_meta['generated_config_source_sha256'],
         'V42 support/config source rules changed')
    need(p.get('updater_sha256') == MANAGED_UPDATER, 'Installed updater dependency differs')
    return dict(policy=p, old_rows=old_rows, old_meta=old_meta, old_formal=old_formal,
                policy_sha256=hashlib.sha256(encoded(p)).hexdigest())


def managed_updater():
    import importlib.util
    path = no_links(Path(__file__).resolve().with_name('local_updater.py'))
    need(path.is_file() and digest(path) == MANAGED_UPDATER, 'Exact embedded LOCAL updater was not extracted')
    spec = importlib.util.spec_from_file_location('accepted_managed_updater', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def managed_verify_tree(root, installed, documents):
    no_links(root)
    for name, raw in documents.items():
        path = under(root, name)
        need(path.is_file() and path.stat().st_nlink == 1 and path.read_bytes() == raw,
             'Managed generated document differs: ' + name)
    for row in installed.values():
        verify(root, row)
        need(under(root, row['path']).stat().st_nlink == 1, 'Managed runtime contains a hard link')


def managed_old_state(workspace, contract, pointer=None):
    if pointer is None:
        pointer = read(workspace / 'releases/local/current.json')
    commit = pointer.get('repository_commit')
    need(isinstance(commit, str) and re.fullmatch('[a-f0-9]{40}|[a-f0-9]{64}', commit), 'Original managed Git identity missing')
    old_meta = contract['old_meta']
    additions = {r['path'] for r in old_meta['support_additions']}
    docs, installed, expected = generated_documents(workspace, old_meta, commit, contract['old_rows'], contract['old_formal'], additions)
    need(pointer == expected, 'Existing managed pointer is not the exact original V42 shape')
    root = under(workspace, expected['path'])
    need(root.parent == workspace / 'releases/local' and root.name == old_meta['release'], 'Original managed release root differs')
    managed_verify_tree(root, installed, docs)
    return dict(pointer=pointer, root=root, documents=docs, installed=installed)


def managed_database_snapshot(path):
    import sqlite3
    from contextlib import closing
    no_links(path)
    need(path.is_file() and path.stat().st_nlink == 1, 'Managed player database path differs')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        need(db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'Managed player database integrity differs')
        need(not db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger'").fetchone(),
             'Unreviewed writer trigger; database preserved')
        objects = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        tables = {}
        for name, sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            quoted = '"' + name.replace('"', '""') + '"'
            values = [json.dumps([(type(v).__name__, v.hex() if isinstance(v, bytes) else v) for v in row],
                                 ensure_ascii=True, separators=(',', ':')) for row in db.execute('SELECT * FROM ' + quoted)]
            tables[name] = dict(sql=sql, rows=sorted(values))
        return hashlib.sha256(json.dumps(dict(objects=objects, tables=tables), ensure_ascii=True, sort_keys=True,
                                         separators=(',', ':')).encode()).hexdigest()


def managed_journal(workspace, u, contract, path):
    path = no_links(Path(path))
    need(path.is_absolute() and path == path.resolve(), 'Managed recovery journal is not canonical')
    need(path.is_relative_to(workspace / 'state/local-updater') and path.name == 'journal.json', 'Managed recovery journal escaped its root')
    j = u.read(path)
    need(j.get('schema') == u.SCHEMA and j.get('kind') == MANAGED_KIND and
         j.get('policy_sha256') == contract['policy_sha256'] and j.get('journal') == str(path),
         'Unrecognized managed recovery journal')
    managed_old_state(workspace, contract, j['parent'])
    return path, j


def managed_recover(workspace, metadata, new_rows, formal, additions):
    contract = managed_policy(metadata, new_rows)
    if contract is None:
        return
    paths = [workspace / 'analysis/coordination-20261015' / n for n in ('active-publication.lock', 'publication-record.lock')]
    present = [p for p in paths if p.exists()]
    if not present:
        return
    u = managed_updater()
    identity = u.read(no_links(present[0]))
    need(identity.get('schema') == u.SCHEMA and identity.get('operation') == 'local-oneclick-updater' and
         all(u.read(no_links(p)) == identity for p in present), 'Foreign managed publication lock; runtime preserved')
    contract = structure_journal_contract(workspace, u, contract, identity['journal'])
    path, j = managed_journal(workspace, u, contract, identity['journal'])
    need(j['token'] == identity['token'] and j['created'] == identity['created'], 'Managed recovery lock/journal differs')
    if j.get('candidate') is not None:
        recorded = j['candidate'].get('repository_commit')
        need(isinstance(recorded, str) and re.fullmatch('[a-f0-9]{40}|[a-f0-9]{64}', recorded), 'Managed candidate Git identity differs')
        _, _, expected = generated_documents(workspace, metadata, recorded, new_rows, formal, additions)
        need(j['candidate'] == expected, 'Foreign candidate pointer prevents managed recovery')
    # The original c976 consumer checks live PID+creation time, exact parent /
    # candidate pointer, normal stop/restart and owns-only lock cleanup.
    u.recover(workspace, u.psutil_for(under(workspace, j['parent']['path'])))


def managed_is_old(workspace, metadata):
    if repair_target(metadata):
        repair_require_bindings()
        current=read(workspace/'releases/local/current.json')
        key=tuple(current.get(k)for k in('release','source_release','source_formal_manifest_sha256'))
        return key in [tuple(r['key'])for r in STRUCTURE_PREDECESSORS]+[(STRUCTURE_RUNTIME_RELEASE,STRUCTURE_SOURCE_RELEASE,STRUCTURE_FORMAL)]+[('local-git-first-run-shared-repair-20261030-v1','local-native-shared-repair-20261030-v1','2291d8c2e24f72209e802de082fda701f623fc87609e201206136f5862ff9fd5')]+[('local-git-first-run-cache-exact41400-20261030-v1', 'local-cache-exact41400-20261030-v1', '7dd7cab0d08b85c9803e0c96d92109d4d5c2d22d729e47c0104d7f8e40d93b35')]+[('local-git-first-run-owned-stones-nine-leaf-20261030-v1', 'local-owned-stones-nine-leaf-20261030-v1', '965f336f1f5f940746eedf51c1c94f57c60abbdffc50e78c025e1da3d4ff3558')]+[('local-git-first-run-accessory-identification-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69')]+[('local-git-first-run-wear-wait-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69')]+[('local-git-first-run-world-event-20261031-v1', 'local-accessory-identification-groups-20261030-v1', '8d7af9132167f8f852dbed7ab42f23cefaf423d239576be4666439c9c9486d69')]
    if structure_target(metadata):
        current = read(workspace / 'releases/local/current.json')
        key = tuple(current.get(k) for k in ('release','source_release','source_formal_manifest_sha256'))
        return any(key == tuple(row['key']) for row in STRUCTURE_PREDECESSORS)
    p = metadata.get('upgrade_from')
    if not isinstance(p, dict):
        return False
    current = read(workspace / 'releases/local/current.json')
    return ((current.get('release'), current.get('source_release'), current.get('source_formal_manifest_sha256')) ==
            ('local-git-first-run-20261029-v1', 'local-native-shop-flow-20261029-v1', MANAGED_OLD_FORMAL))


# Inserted only into the new Repair bootstrap resource. Historical resources and
# the c976 updater remain unchanged. Guard byte payloads are generator-bound.
REPAIR_RECOVERY_GUARD_PAYLOADS = {'els_server/storage/relationships.py': {'base64': 'IiIiQXRvbWljIG9yaWdpbmFsIGNvdXBsZSBwcm9wb3NhbC9hbnN3ZXIsIGltbXV0YWJsZSBkZWJpdCBzb3VyY2UgYW5kIGNvbGQgdmlldy4iIiINCmltcG9ydCBoYXNobGliLGpzb24sc3FsaXRlMyx0aW1lDQpmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLnJlbGF0aW9uc2hpcF9ydWxlcyBpbXBvcnQgUklORyxlbGlnaWJsZQ0KZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnJlbGF0aW9uc2hpcF9tZXNzYWdlcyBpbXBvcnQgcHJvcG9zZV9yZXF1ZXN0LGFuc3dlcl9yZXF1ZXN0DQpmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wucHJvdG9jb2xfY29kZWMgaW1wb3J0IGVuY29kZV9ldmVudA0KZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaXRlbV9hY3RvciBpbXBvcnQgcmVxdWlyZV9hY3RpdmVfY2hhcmFjdGVyDQpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5wcm9mZXNzaW9uX3N0YXRlIGltcG9ydCByZXF1aXJlX293bmVyDQpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pbnZlbnRvcnlfc3RhdGUgaW1wb3J0IGxvYWRfaXRlbXMNCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLml0ZW1faW5zdGFuY2VzIGltcG9ydCByZW1vdmUNClRBQkxFUz0oJ25hdGl2ZV9jb3VwbGVfcGFpcnNfdjEnLCduYXRpdmVfY291cGxlX21lbWJlcnNfdjEnLCduYXRpdmVfY291cGxlX3BlbmRpbmdfdjEnLCduYXRpdmVfY291cGxlX2FjdGlvbnNfdjEnKQ0KU0NIRU1BUz17J25hdGl2ZV9jb3VwbGVfcGFpcnNfdjEnOiAnQ1JFQVRFIFRBQkxFIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEoaWQgVEVYVCBQUklNQVJZIEtFWSxhIElOVEVHRVIgTk9UIE5VTEwsYiBJTlRFR0VSIE5PVCBOVUxMLGFfYWNjb3VudCBJTlRFR0VSIE5PVCBOVUxMLGJfYWNjb3VudCBJTlRFR0VSIE5PVCBOVUxMLGNyZWF0ZWRfYXQgSU5URUdFUiBOT1QgTlVMTCxwcm9wb3NhbCBURVhUIE5PVCBOVUxMLGFjY2VwdGFuY2UgVEVYVCBOT1QgTlVMTCxpdGVtX3VpZCBJTlRFR0VSIE5PVCBOVUxMLHZlcnNpb24gSU5URUdFUiBOT1QgTlVMTCBDSEVDSyh2ZXJzaW9uPTEpKScsICduYXRpdmVfY291cGxlX21lbWJlcnNfdjEnOiAnQ1JFQVRFIFRBQkxFIG5hdGl2ZV9jb3VwbGVfbWVtYmVyc192MShvd25lciBJTlRFR0VSIFBSSU1BUlkgS0VZIFJFRkVSRU5DRVMgY2hhcmFjdGVycyh1aWQpLGFjY291bnRfaWQgSU5URUdFUiBOT1QgTlVMTCxwYWlyX2lkIFRFWFQgTk9UIE5VTEwgUkVGRVJFTkNFUyBuYXRpdmVfY291cGxlX3BhaXJzX3YxKGlkKSknLCAnbmF0aXZlX2NvdXBsZV9wZW5kaW5nX3YxJzogJ0NSRUFURSBUQUJMRSBuYXRpdmVfY291cGxlX3BlbmRpbmdfdjEob3BlcmF0aW9uIFRFWFQgUFJJTUFSWSBLRVkscHJvcG9zZXIgSU5URUdFUiBOT1QgTlVMTCBVTklRVUUscmVjaXBpZW50IElOVEVHRVIgTk9UIE5VTEwgVU5JUVVFLHByb3Bvc2VyX2FjY291bnQgSU5URUdFUiBOT1QgTlVMTCxyZWNpcGllbnRfYWNjb3VudCBJTlRFR0VSIE5PVCBOVUxMLHByb3Bvc2VyX3Nlc3Npb24gVEVYVCBOT1QgTlVMTCxyZWNpcGllbnRfc2Vzc2lvbiBURVhUIE5PVCBOVUxMLGl0ZW1fdWlkIElOVEVHRVIgTk9UIE5VTEwsaXRlbV9qc29uIFRFWFQgTk9UIE5VTEwsY3JlYXRlZF9hdCBJTlRFR0VSIE5PVCBOVUxMLGRlc2NyaXB0b3IgQkxPQiBOT1QgTlVMTCknLCAnbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxJzogJ0NSRUFURSBUQUJMRSBuYXRpdmVfY291cGxlX2FjdGlvbnNfdjEob3BlcmF0aW9uIFRFWFQgUFJJTUFSWSBLRVkscmVxdWVzdF9oYXNoIFRFWFQgTk9UIE5VTEwsa2luZCBJTlRFR0VSIE5PVCBOVUxMLG93bmVyIElOVEVHRVIgTk9UIE5VTEwscGVlciBJTlRFR0VSIE5PVCBOVUxMLHBheWxvYWQgQkxPQiBOT1QgTlVMTCxwcm9wb3NhbCBURVhUIE5PVCBOVUxMLHN0YXR1cyBURVhUIE5PVCBOVUxMLGNyZWF0ZWRfYXQgSU5URUdFUiBOT1QgTlVMTCxiZWZvcmVfanNvbiBURVhUIE5PVCBOVUxMLGFmdGVyX2pzb24gVEVYVCBOT1QgTlVMTCknfQ0KZGVmIF9wcmVzZW50KGRiKToNCiBmb3VuZD1kaWN0KGRiLmV4ZWN1dGUoIlNFTEVDVCBuYW1lLHNxbCBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIobmFtZSkgSU4gKD8sPyw/LD8pIixUQUJMRVMpKQ0KIGlmIGZvdW5kIGFuZCBmb3VuZCE9U0NIRU1BUzpyYWlzZSBWYWx1ZUVycm9yKCdVbmtub3duIG9yIHBhcnRpYWwgY3VycmVudCBjb3VwbGUgc2NoZW1hJykNCiBpZiBkYi5leGVjdXRlKCJTRUxFQ1QgMSBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIodGJsX25hbWUpIElOICg/LD8sPyw/KSBBTkQodHlwZT0ndHJpZ2dlcidPUih0eXBlPSdpbmRleCdBTkQgc3FsIElTIE5PVCBOVUxMKSkgTElNSVQgMSIsVEFCTEVTKS5mZXRjaG9uZSgpOnJhaXNlIFZhbHVlRXJyb3IoJ1VucmV2aWV3ZWQgY291cGxlIHNjaGVtYSBleHRlbnNpb24nKQ0KIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmNvdXBsZV9jbG9zdXJlcyBpbXBvcnQgcHJlc2VudA0KIHByZXNlbnQoZGIsYmFzZT1ib29sKGZvdW5kKSkNCiByZXR1cm4gYm9vbChmb3VuZCkNCmRlZiBfc2NoZW1hKGRiKToNCiBpZiBfcHJlc2VudChkYik6cmV0dXJuDQogaWYgbm90IGRiLmluX3RyYW5zYWN0aW9uOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBzY2hlbWEgb3V0c2lkZSB3cml0ZXIgdHJhbnNhY3Rpb24nKQ0KIGZvciBzcWwgaW4gU0NIRU1BUy52YWx1ZXMoKTpkYi5leGVjdXRlKHNxbCkNCiBfcHJlc2VudChkYikNCmRlZiBfd3JpdGVfZ3VhcmQoZGIpOg0KICMgRXhhY3RseSB0aGUgaW52ZW50b3J5IGFuZCBtZXRhZGF0YSB0YWJsZXMgdG91Y2hlZCBieSBvcmlnaW5hbCByZW1vdmUoKS4NCiAjIEN1cnJlbnQgbmF0aXZlIHN0b3JhZ2UgZGVmaW5lcyBubyB0cmlnZ2VycyBvbiB0aGVzZSB3cml0ZXIgZGVwZW5kZW5jaWVzLg0KIHRhYmxlcz0oJ2ludmVudG9yeV9pdGVtcycsJ2VxdWlwbWVudF9hdHRyaWJ1dGVzJywnZXF1aXBtZW50X2R1cmFiaWxpdHknLCdlcXVpcG1lbnRfZW5oYW5jZW1lbnQnLCdpdGVtX2V4cGlyYXRpb24nLCdpdGVtX2xvY2tzJywnZXF1aXBtZW50X29wdGlvbnMnLCdlcXVpcG1lbnRfaWRlbnRpZmljYXRpb24nLCdlcXVpcG1lbnRfZW5oYW5jZW1lbnRfcHJvZ3Jlc3MnLCdpdGVtX3NlYWxzJywnYXJ0aWZhY3RfZXF1aXBtZW50X3N0YXRlJywnZXF1aXBtZW50X2NoaXBfdHVuaW5nJywnZXF1aXBtZW50X3JlZm9yZ2Vfc3RhdGVzJywnZXF1aXBtZW50X2VuZ3JhdmVfcHJldmlld3MnLCd3YXJkcm9iZV9pdGVtX3N0YXRlJywnd2FyZHJvYmVfZHllcycpDQogaWYgZGIuZXhlY3V0ZSgiU0VMRUNUIDEgRlJPTSBzcWxpdGVfbWFzdGVyIFdIRVJFIHR5cGU9J3RyaWdnZXInQU5EIGxvd2VyKHRibF9uYW1lKSBJTigiKycsJy5qb2luKCc/J2ZvciBfIGluIHRhYmxlcykrJykgTElNSVQgMScsdGFibGVzKS5mZXRjaG9uZSgpOnJhaXNlIFZhbHVlRXJyb3IoJ1VucmV2aWV3ZWQgY291cGxlIGludmVudG9yeSB3cml0ZXIgdHJpZ2dlcicpDQogX3ByZXNlbnQoZGIpDQpkZWYgX2FjdG9yKGRiLHVpZCxhY2NvdW50KToNCiByZXF1aXJlX2FjdGl2ZV9jaGFyYWN0ZXIoZGIsdWlkKTtyZXF1aXJlX293bmVyKGRiLHVpZCxhY2NvdW50KQ0KIHJvdz1kYi5leGVjdXRlKCdTRUxFQ1QgdWlkLG5hbWUsdW5pdF90eXBlIEZST00gY2hhcmFjdGVycyBXSEVSRSB1aWQ9PycsKHVpZCwpKS5mZXRjaG9uZSgpDQogaWYgcm93IGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG1pc3Npbmcgc2F2ZWQgY2hhcmFjdGVyJykNCiByZXR1cm4gZGljdCh6aXAoKCd1aWQnLCduYW1lJywndW5pdF90eXBlJykscm93KSkNCmRlZiBfZGlnZXN0KHVpZCxraW5kLHBheWxvYWQpOnJldHVybiBoYXNobGliLnNoYTI1NihzdHIodWlkKS5lbmNvZGUoKStiJzonK3N0cihraW5kKS5lbmNvZGUoKStiJzonK3BheWxvYWQpLmhleGRpZ2VzdCgpDQpkZWYgX2RlYml0KGJlZm9yZSxhZnRlcixpdGVtX3VpZCk6DQogaWYgbm90IGlzaW5zdGFuY2UoYmVmb3JlLGxpc3Qpb3Igbm90IGlzaW5zdGFuY2UoYWZ0ZXIsbGlzdClvciBhbnkobm90IGlzaW5zdGFuY2UoaSxkaWN0KWZvciBpIGluIGJlZm9yZSthZnRlcik6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHNhdmVkIGludmVudG9yeSByZWNlaXB0IGFycmF5cycpDQogc291cmNlPW5leHQoKGkgZm9yIGkgaW4gYmVmb3JlIGlmIGlbJ3VpZCddPT1pdGVtX3VpZCksTm9uZSkNCiBpZiBzb3VyY2UgaXMgTm9uZSBvcihzb3VyY2VbJ3RlbXBsYXRlJ10sc291cmNlWydtZXRhZGF0YSddLHNvdXJjZVsnZ3JvdXAnXSkhPShSSU5HLDAsNClvciBzb3VyY2VbJ2NvdW50J108MTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3Qgb3JpZ2luYWwgcmluZyBzb3VyY2UgcmVjZWlwdCcpDQogZXhwZWN0ZWQ9W2RpY3QoaSlmb3IgaSBpbiBiZWZvcmVdDQogZm9yIGkgaW4gZXhwZWN0ZWQ6DQogIGlmIGlbJ3VpZCddPT1pdGVtX3VpZDppWydjb3VudCddLT0xDQogZXhwZWN0ZWQ9W2kgZm9yIGkgaW4gZXhwZWN0ZWQgaWYgaVsnY291bnQnXV0NCiBpZiBleHBlY3RlZCE9YWZ0ZXI6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG11c3QgZGViaXQgZXhhY3RseSBvbmUgYm91bmQgcmluZycpDQogcmV0dXJuIHNvdXJjZQ0KZGVmIHNuYXBzaG90KGRiLG93bmVyLGFjY291bnQpOg0KIGlmIGRiLmV4ZWN1dGUoJ1NFTEVDVCBhY2NvdW50X2lkIEZST00gY2hhcmFjdGVyX293bmVycyBXSEVSRSB1aWQ9PycsKG93bmVyLCkpLmZldGNob25lKCkhPShhY2NvdW50LCk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNvbGQgb3duZXInKQ0KIGlmIG5vdCBfcHJlc2VudChkYik6cmV0dXJuIE5vbmUNCiBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5jb3VwbGVfY2xvc3VyZXMgaW1wb3J0IGNsb3NlZF9wYWlycw0KIGNsb3NlZD1jbG9zZWRfcGFpcnMoZGIsb3duZXIsYWNjb3VudCkNCiByb3c9ZGIuZXhlY3V0ZSgnU0VMRUNUIHBhaXJfaWQsYWNjb3VudF9pZCBGUk9NIG5hdGl2ZV9jb3VwbGVfbWVtYmVyc192MSBXSEVSRSBvd25lcj0/Jywob3duZXIsKSkuZmV0Y2hvbmUoKQ0KICMgRXZlcnkgZ2VuZXJhdGlvbiBpbnZvbHZpbmcgdGhpcyBvd25lciBtdXN0IHJldGFpbiBpdHMgdmFsaWRhdGVkIGltbXV0YWJsZQ0KICMgc291cmNlLCBpbmNsdWRpbmcgb2xkIGNsb3N1cmVzIHdoaWxlIGEgbGF0ZXIgcGFpciBpcyBhY3RpdmUuDQogcGFpcnM9e3ZbMF1mb3IgdiBpbiBkYi5leGVjdXRlKCdTRUxFQ1QgaWQgRlJPTSBuYXRpdmVfY291cGxlX3BhaXJzX3YxIFdIRVJFIGE9P09SIGI9PycsKG93bmVyLG93bmVyKSl9DQogaWYgcGFpcnMhPWNsb3NlZHwoe3Jvd1swXX1pZiByb3cgaXMgbm90IE5vbmUgZWxzZSBzZXQoKSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHBhaXIgbGFja3MgbWVtYmVyIG9yIGV4YWN0IGNsb3N1cmUnKQ0KIGlmIHJvdyBpcyBOb25lOnJldHVybiBOb25lDQogaWYgcm93WzFdIT1hY2NvdW50IG9yIHJvd1swXWluIGNsb3NlZDpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgbWVtYmVyIGFjY291bnQgb3IgY2xvc2VkIGdlbmVyYXRpb24nKQ0KIHJldHVybiBfcGFpcl9zbmFwc2hvdChkYixyb3dbMF0sb3duZXIsYWNjb3VudCkNCg0KZGVmIF9wYWlyX3NuYXBzaG90KGRiLHBhaXJfaWQsb3duZXIsYWNjb3VudCwqLGNsb3NlZD1GYWxzZSk6DQogcGFpcj1kYi5leGVjdXRlKCdTRUxFQ1QgYSxiLGFfYWNjb3VudCxiX2FjY291bnQsY3JlYXRlZF9hdCxwcm9wb3NhbCxhY2NlcHRhbmNlLGl0ZW1fdWlkLHZlcnNpb24gRlJPTSBuYXRpdmVfY291cGxlX3BhaXJzX3YxIFdIRVJFIGlkPT8nLChwYWlyX2lkLCkpLmZldGNob25lKCkNCiBpZiBwYWlyIGlzIE5vbmUgb3IgcGFpclstMV0hPTE6cmFpc2UgVmFsdWVFcnJvcignVW5rbm93biBjb3VwbGUgbWVtYmVyL3BhaXInKQ0KIGEsYixhYSxiYSxzdGFtcCxwcm9wb3NhbCxhY2NlcHRhbmNlLGl0ZW1fdWlkLHZlcnNpb249cGFpcg0KIGlmKG93bmVyLGFjY291bnQpbm90IGluKChhLGFhKSwoYixiYSkpOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBleGFjdCBwYWlyIG93bmVyL2FjY291bnQnKQ0KIG1lbWJlcnM9ZGIuZXhlY3V0ZSgnU0VMRUNUIG93bmVyLGFjY291bnRfaWQgRlJPTSBuYXRpdmVfY291cGxlX21lbWJlcnNfdjEgV0hFUkUgcGFpcl9pZD0/IE9SREVSIEJZIG93bmVyJywocGFpcl9pZCwpKS5mZXRjaGFsbCgpDQogaWYgbWVtYmVycyE9KFtdaWYgY2xvc2VkIGVsc2Ugc29ydGVkKFsoYSxhYSksKGIsYmEpXSkpb3IgYT09YiBvciBvd25lciBub3QgaW4oYSxiKW9yIHN0YW1wPD0wOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBleGFjdGx5IHR3byByZWNpcHJvY2FsIG93bmVkIG1lbWJlcnMnKQ0KIGZvciB1aWQsYWlkIGluIHNvcnRlZChbKGEsYWEpLChiLGJhKV0pOg0KICBpZiBkYi5leGVjdXRlKCdTRUxFQ1QgYWNjb3VudF9pZCBGUk9NIGNoYXJhY3Rlcl9vd25lcnMgV0hFUkUgdWlkPT8nLCh1aWQsKSkuZmV0Y2hvbmUoKSE9KGFpZCwpOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBtZW1iZXIgYWNjb3VudCBjaGFuZ2VkJykNCiBhY3Rpb249ZGIuZXhlY3V0ZSgnU0VMRUNUIHJlcXVlc3RfaGFzaCxraW5kLG93bmVyLHBlZXIscGF5bG9hZCxwcm9wb3NhbCxzdGF0dXMsY3JlYXRlZF9hdCxiZWZvcmVfanNvbixhZnRlcl9qc29uIEZST00gbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxIFdIRVJFIG9wZXJhdGlvbj0/JywoYWNjZXB0YW5jZSwpKS5mZXRjaG9uZSgpDQogaWYgYWN0aW9uIGlzIE5vbmUgb3IgYWN0aW9uWzE6NF0hPSgweDNmZSxiLGEpb3IgYWN0aW9uWzU6OF0hPShwcm9wb3NhbCwnYWNjZXB0ZWQnLHN0YW1wKW9yIGFjdGlvblswXSE9X2RpZ2VzdChiLDB4M2ZlLGFjdGlvbls0XSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGxhY2tzIGltbXV0YWJsZSBleGFjdCBhY2NlcHRhbmNlIHByb2R1Y2VyJykNCiBwYXJzZWQ9YW5zd2VyX3JlcXVlc3QoYWN0aW9uWzRdKQ0KIGlmKHBhcnNlZFsnYW5zd2VyJ10scGFyc2VkWydwcm9wb3NlciddLHBhcnNlZFsncmVjaXBpZW50J10pIT0oMCxhLGIpOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBtdXR1YWwgYWNjZXB0YW5jZSBzb3VyY2UgaWRlbnRpdGllcycpDQogc291cmNlPV9kZWJpdChqc29uLmxvYWRzKGFjdGlvbls4XSksanNvbi5sb2FkcyhhY3Rpb25bOV0pLGl0ZW1fdWlkKQ0KIHByb3Bvc2VkPWRiLmV4ZWN1dGUoJ1NFTEVDVCBraW5kLG93bmVyLHBlZXIscGF5bG9hZCxzdGF0dXMscmVxdWVzdF9oYXNoLGJlZm9yZV9qc29uLGFmdGVyX2pzb24gRlJPTSBuYXRpdmVfY291cGxlX2FjdGlvbnNfdjEgV0hFUkUgb3BlcmF0aW9uPT8nLChwcm9wb3NhbCwpKS5mZXRjaG9uZSgpDQogaWYgcHJvcG9zZWQgaXMgTm9uZSBvciBwcm9wb3NlZFs6M10hPSgweDNmYixhLGIpb3IgcHJvcG9zZWRbNF0hPSdwcm9wb3NlZCdvciBwcm9wb3NlZFs1XSE9X2RpZ2VzdChhLDB4M2ZiLHByb3Bvc2VkWzNdKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgbGFja3Mgb3JpZ2luYWwgcHJvcG9zYWwnKQ0KIGlmIHByb3Bvc2VfcmVxdWVzdChwcm9wb3NlZFszXSkhPXBhcnNlZFsnb3duX25hbWUnXW9yIGpzb24ubG9hZHMocHJvcG9zZWRbNl0pIT1bc291cmNlXW9yIHByb3Bvc2VkWzZdIT1wcm9wb3NlZFs3XTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3QgcHJvcG9zYWwgcmluZyBzb3VyY2UgY2hhbmdlZCcpDQogcGVlcj1iIGlmIG93bmVyPT1hIGVsc2UgYTtuYW1lPWRiLmV4ZWN1dGUoJ1NFTEVDVCBuYW1lIEZST00gY2hhcmFjdGVycyBXSEVSRSB1aWQ9PycsKHBlZXIsKSkuZmV0Y2hvbmUoKQ0KIGlmIG5hbWUgaXMgTm9uZTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcGFydG5lciBjaGFyYWN0ZXIgdW5hdmFpbGFibGUnKQ0KIHJldHVybiBkaWN0KHBhaXJfaWQ9cGFpcl9pZCxraW5kPTEscGVlcl91aWQ9cGVlcixwZWVyX25hbWU9bmFtZVswXSxjcmVhdGVkX2F0PXN0YW1wKQ0KZGVmIF9yaW5nKGRiLG93bmVyLCosbm93LHVpZD1Ob25lKToNCiBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLml0ZW1fZXhwaXJhdGlvbiBpbXBvcnQgcmVxdWlyZV9jdXJyZW50DQogZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5pdGVtX2xvY2tzIGltcG9ydCByZXF1aXJlX3VubG9ja2VkDQogY2FuZGlkYXRlcz1baSBmb3IgaSBpbiBsb2FkX2l0ZW1zKGRiLG93bmVyKWlmKGlbJ3RlbXBsYXRlJ10saVsnbWV0YWRhdGEnXSxpWydncm91cCddKT09KFJJTkcsMCw0KWFuZCh1aWQgaXMgTm9uZSBvciBpWyd1aWQnXT09dWlkKV0NCiBmb3IgaXRlbSBpbiBzb3J0ZWQoY2FuZGlkYXRlcyxrZXk9bGFtYmRhIGk6KGlbJ3Nsb3QnXSxpWyd1aWQnXSkpOg0KICB0cnk6DQogICByZXF1aXJlX2N1cnJlbnQoaXRlbSxub3c9bm93KTtyZXF1aXJlX3VubG9ja2VkKGl0ZW0sbm93PW5vdykNCiAgIGlmIGl0ZW0uZ2V0KCdzZWFsZWQnLEZhbHNlKW9yIGl0ZW0uZ2V0KCdzZWFsX2NvdW50JywwKTpjb250aW51ZQ0KICAgcmV0dXJuIGl0ZW0NCiAgZXhjZXB0IFZhbHVlRXJyb3I6Y29udGludWUNCiByYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgbmVlZHMgYSBjdXJyZW50IHVubG9ja2VkIG93bmVkMjY5NzEwJykNCmRlZiBfY2xvY2sobm93KToNCiBub3c9aW50KHRpbWUudGltZSgpKWlmIG5vdyBpcyBOb25lIGVsc2Ugbm93DQogaWYgdHlwZShub3cpaXMgbm90IGludCBvciBub3QgMDxub3c8MioqNjM6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHNlcnZlciBjbG9jaycpDQogcmV0dXJuIG5vdw0KZGVmIF9wcmV2aW91cyhkYixvcGVyYXRpb24sb3duZXIscGVlcixraW5kLHBheWxvYWQpOg0KIGlmIHR5cGUob3BlcmF0aW9uKWlzIG5vdCBzdHIgb3Igbm90IDE8PWxlbihvcGVyYXRpb24pPD0xNjA6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG9wZXJhdGlvbiBpZGVudGl0eScpDQogcm93PWRiLmV4ZWN1dGUoJ1NFTEVDVCByZXF1ZXN0X2hhc2gsb3duZXIscGVlcixraW5kLHN0YXR1cyxwcm9wb3NhbCBGUk9NIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBXSEVSRSBvcGVyYXRpb249PycsKG9wZXJhdGlvbiwpKS5mZXRjaG9uZSgpDQogaWYgcm93IGlzIG5vdCBOb25lIGFuZCByb3dbOjRdIT0oX2RpZ2VzdChvd25lcixraW5kLHBheWxvYWQpLG93bmVyLHBlZXIsa2luZCk6cmFpc2UgVmFsdWVFcnJvcignQ29uZmxpY3RpbmcgY291cGxlIHJlcGxheScpDQogcmV0dXJuIHJvdw0KZGVmIHByb3Bvc2UoZGIsb3duZXIsYWNjb3VudCx0YXJnZXQsdGFyZ2V0X2FjY291bnQsc2Vzc2lvbix0YXJnZXRfc2Vzc2lvbixwYXlsb2FkLG9wZXJhdGlvbiwqLGd1YXJkLGVuY29kZSxub3c9Tm9uZSk6DQogcmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG11dGF0aW9ucyBkaXNhYmxlZCBpbiBmcmVlLWZhcmV3ZWxsIGNvbXBhdGlibGUgcmVjb3ZlcnknKQ0KIG5vdz1fY2xvY2sobm93KTtfd3JpdGVfZ3VhcmQoZGIpO2d1YXJkKGRiKTthPV9hY3RvcihkYixvd25lcixhY2NvdW50KTtiPV9hY3RvcihkYix0YXJnZXQsdGFyZ2V0X2FjY291bnQpO2VsaWdpYmxlKGEsYikNCiBpZiBwcm9wb3NlX3JlcXVlc3QocGF5bG9hZCkhPWJbJ25hbWUnXTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3Qgb25saW5lIHRhcmdldCBuaWNrbmFtZScpDQogaWYgc25hcHNob3QoZGIsb3duZXIsYWNjb3VudClpcyBub3QgTm9uZSBvciBzbmFwc2hvdChkYix0YXJnZXQsdGFyZ2V0X2FjY291bnQpaXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGFjdG9ycyBtdXN0IGJvdGggYmUgc29sbycpDQogX3NjaGVtYShkYik7b2xkPV9wcmV2aW91cyhkYixvcGVyYXRpb24sb3duZXIsdGFyZ2V0LDB4M2ZiLHBheWxvYWQpDQogaWYgb2xkIGlzIE5vbmU6DQogIHJpbmc9X3JpbmcoZGIsb3duZXIsbm93PW5vdykNCiAgcGVuZGluZz1kYi5leGVjdXRlKCdTRUxFQ1Qgb3BlcmF0aW9uLHByb3Bvc2VyLHJlY2lwaWVudCxwcm9wb3Nlcl9zZXNzaW9uLHJlY2lwaWVudF9zZXNzaW9uLGNyZWF0ZWRfYXQgRlJPTSBuYXRpdmVfY291cGxlX3BlbmRpbmdfdjEgV0hFUkUgcHJvcG9zZXIgSU4oPyw/KU9SIHJlY2lwaWVudCBJTig/LD8pJywob3duZXIsdGFyZ2V0LG93bmVyLHRhcmdldCkpLmZldGNoYWxsKCkNCiAgZm9yIG9wLHAsdCxwcyx0cyxjcmVhdGVkIGluIHBlbmRpbmc6DQogICBjdXJyZW50PXtvd25lcjpzZXNzaW9uLHRhcmdldDp0YXJnZXRfc2Vzc2lvbn0NCiAgIGlmIG5vdz5jcmVhdGVkKzEwIG9yIGFueSh1aWQgaW4gY3VycmVudCBhbmQgY3VycmVudFt1aWRdIT1zaWQgZm9yIHVpZCxzaWQgaW4oKHAscHMpLCh0LHRzKSkpOmRiLmV4ZWN1dGUoJ0RFTEVURSBGUk9NIG5hdGl2ZV9jb3VwbGVfcGVuZGluZ192MSBXSEVSRSBvcGVyYXRpb249PycsKG9wLCkpDQogICBlbHNlOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBjdXJyZW50IHBlbmRpbmcgaW52aXRhdGlvbiBleGlzdHMnKQ0KICBkYi5leGVjdXRlKCdJTlNFUlQgSU5UTyBuYXRpdmVfY291cGxlX3BlbmRpbmdfdjEgVkFMVUVTKD8sPyw/LD8sPyw/LD8sPyw/LD8sPyknLChvcGVyYXRpb24sb3duZXIsdGFyZ2V0LGFjY291bnQsdGFyZ2V0X2FjY291bnQsc2Vzc2lvbix0YXJnZXRfc2Vzc2lvbixyaW5nWyd1aWQnXSxqc29uLmR1bXBzKHJpbmcsc29ydF9rZXlzPVRydWUpLG5vdyxwYXlsb2FkKSkNCiAgb3JpZ2luYWxfcmluZz1qc29uLmR1bXBzKFtyaW5nXSxzb3J0X2tleXM9VHJ1ZSkNCiAgZGIuZXhlY3V0ZSgnSU5TRVJUIElOVE8gbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxIFZBTFVFUyg/LD8sPyw/LD8sPyw/LD8sPyw/LD8pJywob3BlcmF0aW9uLF9kaWdlc3Qob3duZXIsMHgzZmIscGF5bG9hZCksMHgzZmIsb3duZXIsdGFyZ2V0LHBheWxvYWQsb3BlcmF0aW9uLCdwcm9wb3NlZCcsbm93LG9yaWdpbmFsX3Jpbmcsb3JpZ2luYWxfcmluZykpDQogZWxzZToNCiAgaWYgb2xkWzQ6XSE9KCdwcm9wb3NlZCcsb3BlcmF0aW9uKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcHJvcG9zYWwgcmVjZWlwdCBzdGF0ZScpDQogIHJpbmc9X3JpbmcoZGIsb3duZXIsbm93PW5vdykNCiByb3c9ZGIuZXhlY3V0ZSgnU0VMRUNUIHByb3Bvc2VyX3Nlc3Npb24scmVjaXBpZW50X3Nlc3Npb24sY3JlYXRlZF9hdCxpdGVtX3VpZCxkZXNjcmlwdG9yIEZST00gbmF0aXZlX2NvdXBsZV9wZW5kaW5nX3YxIFdIRVJFIG9wZXJhdGlvbj0/Jywob3BlcmF0aW9uLCkpLmZldGNob25lKCkNCiBpZiByb3cgaXMgTm9uZSBvciByb3dbOjJdIT0oc2Vzc2lvbix0YXJnZXRfc2Vzc2lvbilvciByb3dbMzpdIT0ocmluZ1sndWlkJ10scGF5bG9hZClvciBub3c+cm93WzJdKzEwOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBleHBpcmVkIG9yIGNoYW5nZWQgcHJvcG9zYWwnKQ0KIGV2ZW50cz1lbmNvZGUoYSxiLEZhbHNlLCgpKQ0KIGZvciBlIGluIGV2ZW50czplbmNvZGVfZXZlbnQoZSkNCiBndWFyZChkYikNCiBfd3JpdGVfZ3VhcmQoZGIpDQogaWYgX2FjdG9yKGRiLG93bmVyLGFjY291bnQpIT1hIG9yIF9hY3RvcihkYix0YXJnZXQsdGFyZ2V0X2FjY291bnQpIT1iOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBsYXRlIGlkZW50aXR5IGNoYW5nZWQnKQ0KIHJldHVybiBldmVudHMNCmRlZiBhbnN3ZXIoZGIsb3duZXIsYWNjb3VudCxwZWVyLHBlZXJfYWNjb3VudCxzZXNzaW9uLHBlZXJfc2Vzc2lvbixwYXlsb2FkLG9wZXJhdGlvbiwqLGd1YXJkLGVuY29kZSxub3c9Tm9uZSk6DQogcmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG11dGF0aW9ucyBkaXNhYmxlZCBpbiBmcmVlLWZhcmV3ZWxsIGNvbXBhdGlibGUgcmVjb3ZlcnknKQ0KIG5vdz1fY2xvY2sobm93KTtfd3JpdGVfZ3VhcmQoZGIpO3BhcnNlZD1hbnN3ZXJfcmVxdWVzdChwYXlsb2FkKTtndWFyZChkYik7dGFyZ2V0PV9hY3RvcihkYixvd25lcixhY2NvdW50KTtwcm9wb3Nlcj1fYWN0b3IoZGIscGVlcixwZWVyX2FjY291bnQpO2VsaWdpYmxlKHByb3Bvc2VyLHRhcmdldCkNCiBpZihwYXJzZWRbJ3Byb3Bvc2VyJ10scGFyc2VkWydyZWNpcGllbnQnXSxwYXJzZWRbJ25hbWUnXSxwYXJzZWRbJ293bl9uYW1lJ10pIT0ocGVlcixvd25lcixwcm9wb3NlclsnbmFtZSddLHRhcmdldFsnbmFtZSddKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgZXhhY3Qgb3JpZ2luYWwgYW5zd2VyIGlkZW50aXRpZXMnKQ0KIGlmIG5vdCBfcHJlc2VudChkYik6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIG1pc3Npbmcgb3JpZ2luYWwgcHJvcG9zYWwgc2NoZW1hJykNCiBvbGQ9X3ByZXZpb3VzKGRiLG9wZXJhdGlvbixvd25lcixwZWVyLDB4M2ZlLHBheWxvYWQpDQogaWYgb2xkIGlzIG5vdCBOb25lOg0KICBzYXZlZD1zbmFwc2hvdChkYixvd25lcixhY2NvdW50KQ0KICBpZiBvbGRbNF09PSdhY2NlcHRlZCdhbmQgc2F2ZWQgaXMgbm90IE5vbmUgYW5kIHNhdmVkWydwYWlyX2lkJ109PW9wZXJhdGlvbiBhbmQgc2F2ZWRbJ3BlZXJfdWlkJ109PXBlZXI6DQogICBldmVudHM9ZW5jb2RlKHByb3Bvc2VyLHRhcmdldCxUcnVlLCgpKTtndWFyZChkYik7cmV0dXJuIGV2ZW50cw0KICBpZiBvbGRbNF09PSdyZWplY3RlZCc6ZXZlbnRzPWVuY29kZShwcm9wb3Nlcix0YXJnZXQsVHJ1ZSwoKSk7Z3VhcmQoZGIpO3JldHVybiBldmVudHMNCiAgcmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHVua25vd24gYW5zd2VyIHJlY2VpcHQnKQ0KIGlmIHNuYXBzaG90KGRiLG93bmVyLGFjY291bnQpaXMgbm90IE5vbmUgb3Igc25hcHNob3QoZGIscGVlcixwZWVyX2FjY291bnQpaXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGFuc3dlciBhZnRlciByZWxhdGlvbiBjaGFuZ2VkJykNCiByb3c9ZGIuZXhlY3V0ZSgnU0VMRUNUIG9wZXJhdGlvbixwcm9wb3Nlcl9hY2NvdW50LHJlY2lwaWVudF9hY2NvdW50LHByb3Bvc2VyX3Nlc3Npb24scmVjaXBpZW50X3Nlc3Npb24saXRlbV91aWQsaXRlbV9qc29uLGNyZWF0ZWRfYXQsZGVzY3JpcHRvciBGUk9NIG5hdGl2ZV9jb3VwbGVfcGVuZGluZ192MSBXSEVSRSBwcm9wb3Nlcj0/QU5EIHJlY2lwaWVudD0/JywocGVlcixvd25lcikpLmZldGNob25lKCkNCiBpZiByb3cgaXMgTm9uZSBvciByb3dbMTo1XSE9KHBlZXJfYWNjb3VudCxhY2NvdW50LHBlZXJfc2Vzc2lvbixzZXNzaW9uKW9yIG5vdz5yb3dbN10rMTAgb3Igcm93WzhdIT1fX2ltcG9ydF9fKCdlbHNfc2VydmVyLnByb3RvY29sLnJlbGF0aW9uc2hpcF9tZXNzYWdlcycsZnJvbWxpc3Q9WydkZXNjcmlwdG9yJ10pLmRlc2NyaXB0b3IodGFyZ2V0WyduYW1lJ10pOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBwZW5kaW5nIHNvdXJjZS9zZXNzaW9uL2RlYWRsaW5lJykNCiBzb3VyY2U9ZGIuZXhlY3V0ZSgnU0VMRUNUIGJlZm9yZV9qc29uLGFmdGVyX2pzb24scGF5bG9hZCxraW5kLG93bmVyLHBlZXIsc3RhdHVzLHJlcXVlc3RfaGFzaCBGUk9NIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBXSEVSRSBvcGVyYXRpb249PycsKHJvd1swXSwpKS5mZXRjaG9uZSgpDQogaWYoc291cmNlIGlzIE5vbmUgb3Igc291cmNlWzBdIT1zb3VyY2VbMV1vciBqc29uLmxvYWRzKHNvdXJjZVswXSkhPVtqc29uLmxvYWRzKHJvd1s2XSldb3Igc291cmNlWzJdIT1yb3dbOF0NCiAgICBvciBzb3VyY2VbMzo3XSE9KDB4M2ZiLHBlZXIsb3duZXIsJ3Byb3Bvc2VkJylvciBzb3VyY2VbN10hPV9kaWdlc3QocGVlciwweDNmYixzb3VyY2VbMl0pKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcGVuZGluZyBsYWNrcyBleGFjdCBpbW11dGFibGUgcHJvcG9zYWwgcmluZyBwcm9kdWNlcicpDQogYmVmb3JlPWxvYWRfaXRlbXMoZGIscGVlcik7Y2hhbmdlcz1bXTtzdGF0dXM9J3JlamVjdGVkJw0KIGlmIHBhcnNlZFsnYW5zd2VyJ109PTA6DQogIHJpbmc9X3JpbmcoZGIscGVlcixub3c9bm93LHVpZD1yb3dbNV0pDQogIGlmIHJpbmchPWpzb24ubG9hZHMocm93WzZdKTpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcHJvcG9zYWwtYm91bmQgcmluZyBjaGFuZ2VkJykNCiAgaWYgcmluZ1snY291bnQnXT09MTpyZW1vdmUoZGIscGVlcixyaW5nKQ0KICBlbGlmIGRiLmV4ZWN1dGUoJ1VQREFURSBpbnZlbnRvcnlfaXRlbXMgU0VUIGNvdW50PWNvdW50LTEgV0hFUkUgb3duZXI9P0FORCB1aWQ9P0FORCBjb3VudD0/JywocGVlcixyaW5nWyd1aWQnXSxyaW5nWydjb3VudCddKSkucm93Y291bnQhPTE6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIHJpbmcgZGViaXQgY2hhbmdlZCcpDQogIGFmdGVyPWxvYWRfaXRlbXMoZGIscGVlcik7X2RlYml0KGJlZm9yZSxhZnRlcixyaW5nWyd1aWQnXSk7cG9zaXRpb249KHJpbmdbJ2dyb3VwJ10scmluZ1snc2xvdCddKTtjaGFuZ2VzPVsocG9zaXRpb24sbmV4dCgoaSBmb3IgaSBpbiBhZnRlciBpZihpWydncm91cCddLGlbJ3Nsb3QnXSk9PXBvc2l0aW9uKSxOb25lKSldO3N0YXR1cz0nYWNjZXB0ZWQnDQogIGRiLmV4ZWN1dGUoJ0lOU0VSVCBJTlRPIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEgVkFMVUVTKD8sPyw/LD8sPyw/LD8sPyw/LDEpJywob3BlcmF0aW9uLHBlZXIsb3duZXIscGVlcl9hY2NvdW50LGFjY291bnQsbm93LHJvd1swXSxvcGVyYXRpb24scmluZ1sndWlkJ10pKQ0KICBkYi5leGVjdXRlbWFueSgnSU5TRVJUIElOVE8gbmF0aXZlX2NvdXBsZV9tZW1iZXJzX3YxIFZBTFVFUyg/LD8sPyknLCgocGVlcixwZWVyX2FjY291bnQsb3BlcmF0aW9uKSwob3duZXIsYWNjb3VudCxvcGVyYXRpb24pKSkNCiBlbHNlOmFmdGVyPWJlZm9yZQ0KIGRiLmV4ZWN1dGUoJ0lOU0VSVCBJTlRPIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBWQUxVRVMoPyw/LD8sPyw/LD8sPyw/LD8sPyw/KScsKG9wZXJhdGlvbixfZGlnZXN0KG93bmVyLDB4M2ZlLHBheWxvYWQpLDB4M2ZlLG93bmVyLHBlZXIscGF5bG9hZCxyb3dbMF0sc3RhdHVzLG5vdyxqc29uLmR1bXBzKGJlZm9yZSxzb3J0X2tleXM9VHJ1ZSksanNvbi5kdW1wcyhhZnRlcixzb3J0X2tleXM9VHJ1ZSkpKQ0KIGRiLmV4ZWN1dGUoJ0RFTEVURSBGUk9NIG5hdGl2ZV9jb3VwbGVfcGVuZGluZ192MSBXSEVSRSBvcGVyYXRpb249PycsKHJvd1swXSwpKQ0KIGV2ZW50cz1lbmNvZGUocHJvcG9zZXIsdGFyZ2V0LEZhbHNlLGNoYW5nZXMpDQogZm9yIGUgaW4gZXZlbnRzOmVuY29kZV9ldmVudChlKQ0KIGd1YXJkKGRiKQ0KIGlmIHBhcnNlZFsnYW5zd2VyJ109PTA6DQogIGlmIGxvYWRfaXRlbXMoZGIscGVlcikhPWFmdGVyOnJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBpbnZlbnRvcnkgY2hhbmdlZCBhZnRlciBleGFjdCBkZWJpdCByZWNlaXB0JykNCiAgX2RlYml0KGJlZm9yZSxsb2FkX2l0ZW1zKGRiLHBlZXIpLHJvd1s1XSkNCiAgaWYgc25hcHNob3QoZGIsb3duZXIsYWNjb3VudClbJ3BlZXJfdWlkJ10hPXBlZXIgb3Igc25hcHNob3QoZGIscGVlcixwZWVyX2FjY291bnQpWydwZWVyX3VpZCddIT1vd25lcjpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgcmVjaXByb2NhbCBjb2xkIHNvdXJjZSBjaGFuZ2VkJykNCiBfd3JpdGVfZ3VhcmQoZGIpDQogaWYgX2FjdG9yKGRiLG93bmVyLGFjY291bnQpIT10YXJnZXQgb3IgX2FjdG9yKGRiLHBlZXIscGVlcl9hY2NvdW50KSE9cHJvcG9zZXI6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGxhdGUgc2F2ZWQgY2hhcmFjdGVyIGNoYW5nZWQnKQ0KIHJldHVybiBldmVudHMNCg==', 'size': 15544, 'sha256': 'ddb601d64ed6100187f945a34b997483f6198c9338fb9010ea032cc927d63e3c'}, 'els_server/storage/couple_closures.py': {'base64': 'IiIiRXhhY3QgbGF6eSBjbG9zdXJlIGxlZGdlciBmb3IgaHVtYW4tYXBwcm92ZWQgZnJlZSBjb3VwbGUxIGZhcmV3ZWxsLg0KT2xkIHBhaXIvYWNjZXB0YW5jZS9wcm9wb3NhbC9kZWJpdCBmYWN0cyByZW1haW4gaW1tdXRhYmxlOyBvbmx5IGFjdGl2ZSBtZW1iZXJzaGlwcw0KYXJlIHJlbW92ZWQuIE5vIEVEL2ludmVudG9yeS9yZWZ1bmQgd3JpdGVyIGFuZCBubyBndWVzc2VkIG1hcnJpYWdlIHBvbGljeS4NCiIiIg0KaW1wb3J0IGpzb24NCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlIGltcG9ydCByZWxhdGlvbnNoaXBzIGFzIHJlbA0KZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnJlbGF0aW9uc2hpcF9tZXNzYWdlcyBpbXBvcnQgZmFyZXdlbGxfcmVxdWVzdA0KZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQNClRBQkxFPSduYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxJw0KUE9MSUNZPSdodW1hbi1mcmVlLWNvdXBsZTEtbm8tcmluZy1yZWZ1bmQtMjAyNjEwMjktdjEnDQpTQ0hFTUE9IkNSRUFURSBUQUJMRSBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxKHBhaXJfaWQgVEVYVCBQUklNQVJZIEtFWSBSRUZFUkVOQ0VTIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEoaWQpLG9wZXJhdGlvbiBURVhUIE5PVCBOVUxMIFVOSVFVRSxyZXF1ZXN0X2hhc2ggVEVYVCBOT1QgTlVMTCxvd25lciBJTlRFR0VSIE5PVCBOVUxMLGFjY291bnRfaWQgSU5URUdFUiBOT1QgTlVMTCxwZWVyIElOVEVHRVIgTk9UIE5VTEwscGVlcl9hY2NvdW50IElOVEVHRVIgTk9UIE5VTEwsY3JlYXRlZF9hdCBJTlRFR0VSIE5PVCBOVUxMLGZlZSBJTlRFR0VSIE5PVCBOVUxMIENIRUNLKGZlZT0wKSxyZWZ1bmQgSU5URUdFUiBOT1QgTlVMTCBDSEVDSyhyZWZ1bmQ9MCksYmVmb3JlX2pzb24gVEVYVCBOT1QgTlVMTCxhZnRlcl9qc29uIFRFWFQgTk9UIE5VTEwscGF5bG9hZCBCTE9CIE5PVCBOVUxMLHBvbGljeSBURVhUIE5PVCBOVUxMLHZlcnNpb24gSU5URUdFUiBOT1QgTlVMTCBDSEVDSyh2ZXJzaW9uPTEpKSINCg0KZGVmIGNhbm9uaWNhbCh2YWx1ZSk6cmV0dXJuIGpzb24uZHVtcHModmFsdWUsc29ydF9rZXlzPVRydWUsc2VwYXJhdG9ycz0oJywnLCc6JykpDQoNCmRlZiBwcmVzZW50KGRiLCosYmFzZT1UcnVlKToNCiBmb3VuZD1kaWN0KGRiLmV4ZWN1dGUoIlNFTEVDVCBuYW1lLHNxbCBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIobmFtZSk9PyIsKFRBQkxFLCkpKQ0KIGlmIGZvdW5kIGFuZChmb3VuZCE9e1RBQkxFOlNDSEVNQX1vciBub3QgYmFzZSk6cmFpc2UgVmFsdWVFcnJvcignVW5rbm93biBvciBvcnBoYW4gY291cGxlIGNsb3N1cmUgc2NoZW1hJykNCiBpZiBkYi5leGVjdXRlKCJTRUxFQ1QgMSBGUk9NIHNxbGl0ZV9tYXN0ZXIgV0hFUkUgbG93ZXIodGJsX25hbWUpPT9BTkQodHlwZT0ndHJpZ2dlcidPUih0eXBlPSdpbmRleCdBTkQgc3FsIElTIE5PVCBOVUxMKSkgTElNSVQgMSIsKFRBQkxFLCkpLmZldGNob25lKCk6cmFpc2UgVmFsdWVFcnJvcignVW5yZXZpZXdlZCBjb3VwbGUgY2xvc3VyZSBzY2hlbWEgZXh0ZW5zaW9uJykNCiByZXR1cm4gYm9vbChmb3VuZCkNCg0KZGVmIGluaXRpYWxpemUoZGIpOg0KIGlmIG5vdCBkYi5pbl90cmFuc2FjdGlvbjpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgY2xvc3VyZSBvdXRzaWRlIHdyaXRlciB0cmFuc2FjdGlvbicpDQogaWYgbm90IHJlbC5fcHJlc2VudChkYik6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNsb3N1cmUgcmVxdWlyZXMgb3JpZ2luYWwgYWNjZXB0ZWQgc2NoZW1hJykNCiBpZiBub3QgcHJlc2VudChkYik6ZGIuZXhlY3V0ZShTQ0hFTUEpDQogcHJlc2VudChkYikNCg0KZGVmIHBhaXJfcm93KGRiLHBhaXJfaWQpOg0KIHJvdz1kYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9wYWlyc192MSBXSEVSRSBpZD0/JywocGFpcl9pZCwpKS5mZXRjaG9uZSgpDQogaWYgcm93IGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignTWlzc2luZyBvcmlnaW5hbCBjb3VwbGUgcGFpcicpDQogcmV0dXJuIHJvdw0KDQpkZWYgcmVjZWlwdF9iZWZvcmUocGFpcixvd25lcixhY2NvdW50KToNCiByZXR1cm4gY2Fub25pY2FsKGRpY3QocGFpcj1saXN0KHBhaXIpLG1lbWJlcnM9c29ydGVkKFtbcGFpclsxXSxwYWlyWzNdLHBhaXJbMF1dLFtwYWlyWzJdLHBhaXJbNF0scGFpclswXV1dKSxhY3Rvcj1bb3duZXIsYWNjb3VudF0pKQ0KDQpkZWYgcmVjZWlwdF9hZnRlcihwYWlyX2lkKTpyZXR1cm4gY2Fub25pY2FsKGRpY3QocGFpcl9pZD1wYWlyX2lkLG1lbWJlcnM9W10sZmVlX0VEPTAscmluZ19yZWZ1bmQ9RmFsc2UpKQ0KDQpkZWYgY2hlY2tlZChkYixyb3cpOg0KIHBhaXJfaWQsb3BlcmF0aW9uLGRpZ2VzdCxvd25lcixhY2NvdW50LHBlZXIscGVlcl9hY2NvdW50LHN0YW1wLGZlZSxyZWZ1bmQsYmVmb3JlLGFmdGVyLHBheWxvYWQscG9saWN5LHZlcnNpb249cm93DQogcGFpcj1wYWlyX3JvdyhkYixwYWlyX2lkKQ0KIGlmKHR5cGUob3BlcmF0aW9uKWlzIG5vdCBzdHIgb3Igbm90IDE8PWxlbihvcGVyYXRpb24pPD0xNjAgb3IgcGF5bG9hZCE9Yicnb3IgZGlnZXN0IT1yZWwuX2RpZ2VzdChvd25lciwweDQxYyxwYXlsb2FkKQ0KICBvcihvd25lcixhY2NvdW50LHBlZXIscGVlcl9hY2NvdW50KW5vdCBpbigocGFpclsxXSxwYWlyWzNdLHBhaXJbMl0scGFpcls0XSksKHBhaXJbMl0scGFpcls0XSxwYWlyWzFdLHBhaXJbM10pKQ0KICBvciB0eXBlKHN0YW1wKWlzIG5vdCBpbnQgb3Igbm90IHBhaXJbNV08PXN0YW1wPDIqKjYzIG9yIGZlZSE9MCBvciByZWZ1bmQhPTAgb3IgcG9saWN5IT1QT0xJQ1kgb3IgdmVyc2lvbiE9MQ0KICBvciBiZWZvcmUhPXJlY2VpcHRfYmVmb3JlKHBhaXIsb3duZXIsYWNjb3VudClvciBhZnRlciE9cmVjZWlwdF9hZnRlcihwYWlyX2lkKSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNsb3N1cmUgaW1tdXRhYmxlIHNvdXJjZSByZWNlaXB0IGNoYW5nZWQnKQ0KIHJlbC5fcGFpcl9zbmFwc2hvdChkYixwYWlyX2lkLG93bmVyLGFjY291bnQsY2xvc2VkPVRydWUpDQogcmV0dXJuIHBhaXJfaWQNCg0KZGVmIGNsb3NlZF9wYWlycyhkYixvd25lcixhY2NvdW50KToNCiBpZiBub3QgcHJlc2VudChkYik6cmV0dXJuIHNldCgpDQogcm93cz1kYi5leGVjdXRlKCdTRUxFQ1QgYy4qRlJPTSBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxIGMgTEVGVCBKT0lOIG5hdGl2ZV9jb3VwbGVfcGFpcnNfdjEgcCBPTiBwLmlkPWMucGFpcl9pZCBXSEVSRSBjLm93bmVyPT9PUiBjLnBlZXI9P09SIHAuYT0/T1IgcC5iPT8nLChvd25lcixvd25lcixvd25lcixvd25lcikpLmZldGNoYWxsKCkNCiByZXN1bHQ9c2V0KCkNCiBmb3Igcm93IGluIHJvd3M6DQogIGlkZW50PWNoZWNrZWQoZGIscm93KTtwYWlyPXBhaXJfcm93KGRiLGlkZW50KQ0KICBpZihvd25lcixhY2NvdW50KW5vdCBpbigocGFpclsxXSxwYWlyWzNdKSwocGFpclsyXSxwYWlyWzRdKSk6cmFpc2UgVmFsdWVFcnJvcignQ291cGxlIGNsb3NlZCBoaXN0b3J5IG93bmVyIGNoYW5nZWQnKQ0KICByZXN1bHQuYWRkKGlkZW50KQ0KIHJldHVybiByZXN1bHQNCg0KZGVmIHF1b3RlKGRiLG93bmVyLGFjY291bnQpOg0KIHNhdmVkPXJlbC5zbmFwc2hvdChkYixvd25lcixhY2NvdW50KQ0KIGlmIHNhdmVkIGlzIE5vbmUgb3Igc2F2ZWRbJ2tpbmQnXSE9MTpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCByZXF1aXJlcyBjdXJyZW50IGNvdXBsZTEnKQ0KIHBhaXI9cGFpcl9yb3coZGIsc2F2ZWRbJ3BhaXJfaWQnXSk7cGVlcj1zYXZlZFsncGVlcl91aWQnXTtwZWVyX2FjY291bnQ9cGFpcls0XWlmIG93bmVyPT1wYWlyWzFdZWxzZSBwYWlyWzNdDQogb3RoZXI9cmVsLnNuYXBzaG90KGRiLHBlZXIscGVlcl9hY2NvdW50KQ0KIGlmIG90aGVyIGlzIE5vbmUgb3Iob3RoZXJbJ3BhaXJfaWQnXSxvdGhlclsncGVlcl91aWQnXSkhPShzYXZlZFsncGFpcl9pZCddLG93bmVyKTpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCByZWNpcHJvY2FsIHBhaXIgY2hhbmdlZCcpDQogcmV0dXJuIGRpY3Qoc2F2ZWQsb3duZXI9b3duZXIsYWNjb3VudF9pZD1hY2NvdW50LHBlZXJfYWNjb3VudD1wZWVyX2FjY291bnQpDQoNCmRlZiBwZXJmb3JtKGRiLG93bmVyLGFjY291bnQscGF5bG9hZCxvcGVyYXRpb24sZXhwZWN0ZWQsKixndWFyZCxlbmNvZGUsbm93PU5vbmUpOg0KIHJhaXNlIFZhbHVlRXJyb3IoJ0NvdXBsZSBtdXRhdGlvbnMgZGlzYWJsZWQgaW4gZnJlZS1mYXJld2VsbCBjb21wYXRpYmxlIHJlY292ZXJ5JykNCiBmYXJld2VsbF9yZXF1ZXN0KHBheWxvYWQpDQogaWYgdHlwZShvcGVyYXRpb24paXMgbm90IHN0ciBvciBub3QgMTw9bGVuKG9wZXJhdGlvbik8PTE2MDpyYWlzZSBWYWx1ZUVycm9yKCdDb3VwbGUgY2xvc3VyZSBvcGVyYXRpb24nKQ0KIGlmIG5vdCBkYi5pbl90cmFuc2FjdGlvbjpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCByZXF1aXJlcyBjYWxsZXIgd3JpdGVyJykNCiBndWFyZChkYik7cmVsLl93cml0ZV9ndWFyZChkYik7cmVsLl9hY3RvcihkYixvd25lcixhY2NvdW50KQ0KIGlmIHByZXNlbnQoZGIpOg0KICBwcmV2aW91cz1kYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9jbG9zdXJlc192MSBXSEVSRSBvcGVyYXRpb249PycsKG9wZXJhdGlvbiwpKS5mZXRjaG9uZSgpDQogIGlmIHByZXZpb3VzIGlzIG5vdCBOb25lOg0KICAgY2hlY2tlZChkYixwcmV2aW91cykNCiAgIGlmIHByZXZpb3VzWzM6NV0hPShvd25lcixhY2NvdW50KW9yIHByZXZpb3VzWzJdIT1yZWwuX2RpZ2VzdChvd25lciwweDQxYyxwYXlsb2FkKW9yIHJlbC5zbmFwc2hvdChkYixvd25lcixhY2NvdW50KWlzIG5vdCBOb25lOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIHJlcGxheSBtZWV0cyBhbm90aGVyIHBhaXIgb3IgaWRlbnRpdHknKQ0KICAgYW5zd2VyPWVuY29kZShUcnVlKTtndWFyZChkYikNCiAgIGZvciBldmVudCBpbiBhbnN3ZXI6ZW5jb2RlX2V2ZW50KGV2ZW50KQ0KICAgcmV0dXJuIGFuc3dlcg0KIGFjdHVhbD1xdW90ZShkYixvd25lcixhY2NvdW50KQ0KIGlmIGFjdHVhbCE9ZXhwZWN0ZWQ6cmFpc2UgVmFsdWVFcnJvcignRmFyZXdlbGwgcXVvdGUgYmVsb25ncyB0byBhbm90aGVyIHBhaXIgZ2VuZXJhdGlvbicpDQogZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaW52ZW50b3J5X3N0YXRlIGltcG9ydCBsb2FkX2l0ZW1zDQogZGVmIGVjb25vbWljKCk6DQogIHJldHVybihbbG9hZF9pdGVtcyhkYix1aWQpZm9yIHVpZCBpbihvd25lcixhY3R1YWxbJ3BlZXJfdWlkJ10pXSxkYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gcmV3YXJkX2JhbGFuY2VzIFdIRVJFIHVpZCBJTig/LD8pT1JERVIgQlkgdWlkJywob3duZXIsYWN0dWFsWydwZWVyX3VpZCddKSkuZmV0Y2hhbGwoKSkNCiBlY29ub215PWVjb25vbWljKCkNCiBzdGFtcD1yZWwuX2Nsb2NrKG5vdykNCiBpZiBzdGFtcDxhY3R1YWxbJ2NyZWF0ZWRfYXQnXTpyYWlzZSBWYWx1ZUVycm9yKCdGYXJld2VsbCBwcmVjZWRlcyB0cnVlIHBhaXJpbmcnKQ0KIHBhaXI9cGFpcl9yb3coZGIsYWN0dWFsWydwYWlyX2lkJ10pO29sZF9wYWlycz1kYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9wYWlyc192MSBPUkRFUiBCWSBpZCcpLmZldGNoYWxsKCk7b2xkX2FjdGlvbnM9ZGIuZXhlY3V0ZSgnU0VMRUNUICpGUk9NIG5hdGl2ZV9jb3VwbGVfYWN0aW9uc192MSBPUkRFUiBCWSBvcGVyYXRpb24nKS5mZXRjaGFsbCgpDQogaW5pdGlhbGl6ZShkYikNCiBkYi5leGVjdXRlKCdJTlNFUlQgSU5UTyBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxIFZBTFVFUyg/LD8sPyw/LD8sPyw/LD8sPyw/LD8sPyw/LD8sMSknLChhY3R1YWxbJ3BhaXJfaWQnXSxvcGVyYXRpb24scmVsLl9kaWdlc3Qob3duZXIsMHg0MWMscGF5bG9hZCksb3duZXIsYWNjb3VudCxhY3R1YWxbJ3BlZXJfdWlkJ10sYWN0dWFsWydwZWVyX2FjY291bnQnXSxzdGFtcCwwLDAscmVjZWlwdF9iZWZvcmUocGFpcixvd25lcixhY2NvdW50KSxyZWNlaXB0X2FmdGVyKGFjdHVhbFsncGFpcl9pZCddKSxwYXlsb2FkLFBPTElDWSkpDQogaWYgZGIuZXhlY3V0ZSgnREVMRVRFIEZST00gbmF0aXZlX2NvdXBsZV9tZW1iZXJzX3YxIFdIRVJFIHBhaXJfaWQ9PycsKGFjdHVhbFsncGFpcl9pZCddLCkpLnJvd2NvdW50IT0yOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIGV4YWN0bHkgdHdvIGFjdGl2ZSBtZW1iZXJzJykNCiBpZiByZWwuc25hcHNob3QoZGIsb3duZXIsYWNjb3VudClpcyBub3QgTm9uZSBvciByZWwuc25hcHNob3QoZGIsYWN0dWFsWydwZWVyX3VpZCddLGFjdHVhbFsncGVlcl9hY2NvdW50J10paXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignRmFyZXdlbGwgYm90aCBjb2xkIHByb2plY3Rpb25zIG11c3QgYmUgc29sbycpDQogYW5zd2VyPWVuY29kZShGYWxzZSkNCiBmb3IgZXZlbnQgaW4gYW5zd2VyOmVuY29kZV9ldmVudChldmVudCkNCiBndWFyZChkYik7cmVsLl93cml0ZV9ndWFyZChkYikNCiBpZiBkYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9wYWlyc192MSBPUkRFUiBCWSBpZCcpLmZldGNoYWxsKCkhPW9sZF9wYWlycyBvciBkYi5leGVjdXRlKCdTRUxFQ1QgKkZST00gbmF0aXZlX2NvdXBsZV9hY3Rpb25zX3YxIE9SREVSIEJZIG9wZXJhdGlvbicpLmZldGNoYWxsKCkhPW9sZF9hY3Rpb25zOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIGFsdGVyZWQgaW1tdXRhYmxlIHBhaXJpbmcvZGViaXQgc291cmNlJykNCiBpZiBlY29ub21pYygpIT1lY29ub215OnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIG11c3QgcHJlc2VydmUgYWxsIG93bmVkIFVJRCBpbnZlbnRvcnkgYW5kIEVEJykNCiBpZiBjaGVja2VkKGRiLGRiLmV4ZWN1dGUoJ1NFTEVDVCAqRlJPTSBuYXRpdmVfY291cGxlX2Nsb3N1cmVzX3YxIFdIRVJFIG9wZXJhdGlvbj0/Jywob3BlcmF0aW9uLCkpLmZldGNob25lKCkpIT1wYWlyWzBdOnJhaXNlIFZhbHVlRXJyb3IoJ0ZhcmV3ZWxsIGZpbmFsIGNsb3N1cmUgcmVjZWlwdCcpDQogcmV0dXJuIGFuc3dlcg0K', 'size': 7065, 'sha256': '4008884caac32d2e8d6393e15d095416015283c82c179c9a252925d1cc639dbe'}, 'els_server/storage/identification_ui.py': {'size': 5446, 'sha256': '9ff48abd45a634a2838a6e9efa1275a7537c655ab5901d66ae4e707c51b30555', 'base64': 'IiIiUmVzZXQgc2Nyb2xsIC0+IHVuaWRlbnRpZmllZCBpdGVtIC0+IHBhaWQtb25jZSBzY3JvbGwgYW5kIGZyZWUgaWRlbnRpZmljYXRpb24uIiIiCmltcG9ydCBzcWxpdGUzLHNlY3JldHMKZnJvbSBjb250ZXh0bGliIGltcG9ydCBjbG9zaW5nCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLnByb2Zlc3Npb25fc3RhdGUgaW1wb3J0IHJlcXVpcmVfb3duZXIKZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5pZGVudGlmaWNhdGlvbl91aSBpbXBvcnQgcmVxdWlyZV90ZW1wbGF0ZSxjYXRhbG9nLGRyYXdfaW5pdGlhbApmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLml0ZW1fZXhwaXJhdGlvbiBpbXBvcnQgcmVxdWlyZV9jdXJyZW50CmZyb20gZWxzX3NlcnZlci5kb21haW4uaXRlbV9sb2NrcyBpbXBvcnQgcmVxdWlyZV91bmxvY2tlZApmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wuaWRlbnRpZmljYXRpb25fbWVzc2FnZXMgaW1wb3J0IHJlcXVlc3QsYWNrbm93bGVkZ2VtZW50CmZyb20gZWxzX3NlcnZlci5wcm90b2NvbC5wcm90b2NvbF9jb2RlYyBpbXBvcnQgRXZlbnQKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaW52ZW50b3J5X2FjdGlvbnMgaW1wb3J0IF9pZGVudGl0eSxfcHJldmlvdXMsX2NvbW1pdApmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pbnZlbnRvcnlfc3RhdGUgaW1wb3J0IGxvYWRfaXRlbXMKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuZXF1aXBtZW50X3JlY2VpcHRfc3RhdGUgaW1wb3J0IGN1cnJlbnRfY2hhbmdlcwpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pdGVtX2luc3RhbmNlcyBpbXBvcnQgcmVtb3ZlCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLm5wY190cmFkZSBpbXBvcnQgYmFsYW5jZXMKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuZXF1aXBtZW50X29wdGlvbnMgaW1wb3J0IHJlcGxhY2UgYXMgcmVwbGFjZV9vcHRpb25zCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmVxdWlwbWVudF9pZGVudGlmaWNhdGlvbiBpbXBvcnQgcmVwbGFjZSBhcyByZXBsYWNlX2lkZW50aWZpZWQKZGVmIHBlcmZvcm0ocGF0aCxvd25lcixraW5kLHBheWxvYWQsb3BlcmF0aW9uLHJhbmRiZWxvdz1zZWNyZXRzLnJhbmRiZWxvdywqLGFjY291bnRfaWQ9Tm9uZSxwcmVwYXJlPU5vbmUpOgogdWlkLG1hdGVyaWFsX3VpZD1yZXF1ZXN0KGtpbmQscGF5bG9hZCk7b3duZXIsZGlnZXN0PV9pZGVudGl0eShvd25lcixraW5kLHBheWxvYWQsb3BlcmF0aW9uKQogd2l0aCBjbG9zaW5nKHNxbGl0ZTMuY29ubmVjdChwYXRoLHRpbWVvdXQ9MTApKSBhcyBkYixkYjoKICBkYi5leGVjdXRlKCdQUkFHTUEgZm9yZWlnbl9rZXlzPU9OJyk7ZGIuZXhlY3V0ZSgnQkVHSU4gSU1NRURJQVRFJykKICBpZiBwcmVwYXJlIGlzIG5vdCBOb25lOnByZXBhcmUoKQogIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLml0ZW1fYWN0b3IgaW1wb3J0IHJlcXVpcmVfYWN0aXZlX2NoYXJhY3RlcgogIHJlcXVpcmVfYWN0aXZlX2NoYXJhY3RlcihkYixvd25lcikKICBpZiBhY2NvdW50X2lkIGlzIG5vdCBOb25lOnJlcXVpcmVfb3duZXIoZGIsb3duZXIsYWNjb3VudF9pZCkKICBvbGQ9X3ByZXZpb3VzKGRiLG9wZXJhdGlvbixkaWdlc3QpO2JlZm9yZT1sb2FkX2l0ZW1zKGRiLG93bmVyKTtlZD1iYWxhbmNlcyhkYixvd25lcilbJ2VkJ107YnlfdWlkPXtpWyd1aWQnXTppIGZvciBpIGluIGJlZm9yZX0KICBpZiBvbGQgaXMgbm90IE5vbmU6CiAgIGN1cnJlbnQ9eyhpWydncm91cCddLGlbJ3Nsb3QnXSk6aSBmb3IgaSBpbiBiZWZvcmV9CiAgIHJldHVybiBbRXZlbnQoMHgyMDEsa2luZD1raW5kKzEscGF5bG9hZD1hY2tub3dsZWRnZW1lbnQoa2luZCxlZCxjdXJyZW50X2NoYW5nZXMoZGIsb3BlcmF0aW9uLG93bmVyLGtpbmQsb2xkLGJlZm9yZSkpKV0KICBpdGVtPWJ5X3VpZC5nZXQodWlkKQogIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfZ2Vhcl9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkIGFzIGFjdGl2aXR5X3N1cHBvcnRlZCxkcmF3IGFzIGFjdGl2aXR5X2RyYXcKICBhY3Rpdml0eT1pdGVtIGlzIG5vdCBOb25lIGFuZCBhY3Rpdml0eV9zdXBwb3J0ZWQoaXRlbVsndGVtcGxhdGUnXSkKICBpZiBhY3Rpdml0eSBhbmQga2luZCE9MHg0Mzg6cmFpc2UgVmFsdWVFcnJvcignQWN0aXZpdHkgYXJtb3Igb3JkaW5hcnkgaW5pdGlhbCBpZGVudGlmaWNhdGlvbiBvbmx5JykKICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmFjY2Vzc29yeV9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkIGFzIGFjY2Vzc29yeV9zdXBwb3J0ZWQsZHJhdyBhcyBhY2Nlc3NvcnlfZHJhdwogIGFjY2Vzc29yeT1pdGVtIGlzIG5vdCBOb25lIGFuZCBhY2Nlc3Nvcnlfc3VwcG9ydGVkKGl0ZW1bJ3RlbXBsYXRlJ10pCiAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hY2Nlc3NvcnlfaWRlbnRpZmljYXRpb24gaW1wb3J0IHByb2ZpbGUgYXMgYWNjZXNzb3J5X3Byb2ZpbGUKICBpZiBhY2Nlc3NvcnkgYW5kIGFjY2Vzc29yeV9wcm9maWxlKGl0ZW1bJ3RlbXBsYXRlJ10paXMgbm90IE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQWNjZXNzb3J5IGlkZW50aWZpY2F0aW9uIG1haW50ZW5hbmNlJykKICBpZiBhY2Nlc3Nvcnk6CiAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYWNjZXNzb3J5X2lkZW50aWZpY2F0aW9uIGltcG9ydCByZXNldF9zdXBwb3J0ZWQKICAgaWYgaXRlbVsnZ3JvdXAnXSE9MiBvciBraW5kPT0weDQzYSBhbmQgbm90IHJlc2V0X3N1cHBvcnRlZChpdGVtWyd0ZW1wbGF0ZSddKTpyYWlzZSBWYWx1ZUVycm9yKCdBY2Nlc3NvcnkgaWRlbnRpZmljYXRpb24gcmVxdWlyZXMgYW4gZWxpZ2libGUgYmFnIGl0ZW0nKQogIGlmIGl0ZW0gaXMgTm9uZSBvciBpdGVtWydjb3VudCddIT0xIG9yKGl0ZW1bJ2dyb3VwJ10hPTEgYW5kIG5vdCBhY2Nlc3NvcnkpOnJhaXNlIFZhbHVlRXJyb3IoJ093bmVkIHVuZXF1aXBwZWQgaWRlbnRpZmljYXRpb24gaXRlbSByZXF1aXJlZCcpCiAgcmVxdWlyZV90ZW1wbGF0ZShpdGVtWyd0ZW1wbGF0ZSddLHJlc2V0PWtpbmQ9PTB4NDNhKTtyZXF1aXJlX2N1cnJlbnQoaXRlbSk7cmVxdWlyZV91bmxvY2tlZChpdGVtKQogIGZyb20gZWxzX3NlcnZlci5kb21haW4uaWRlbnRpZmljYXRpb25fdWkgaW1wb3J0IGluaXRpYWxfcGVuZGluZwogIGZyb20gZWxzX3NlcnZlci5kb21haW4uaWRlbnRpZmljYXRpb25fdWkgaW1wb3J0IGNvbXBhdGliaWxpdHlfcHJvZmlsZQogIGlmIGNvbXBhdGliaWxpdHlfcHJvZmlsZShpdGVtWyd0ZW1wbGF0ZSddKWlzIG5vdCBOb25lOnJhaXNlIFZhbHVlRXJyb3IoJ0NvbXBhdGliaWxpdHkgaWRlbnRpZmljYXRpb24gcmVjb3ZlcnkgZGVuaWVzIG5ldyBvcGVyYXRpb24nKQogIGlkZW50aWZpZWQ9aXRlbS5nZXQoJ2lkZW50aWZpZWQnLG5vdCBpbml0aWFsX3BlbmRpbmcoaXRlbSkpO3ByZXZpb3VzPWl0ZW0uZ2V0KCdvcHRpb25fZ3JvdXBzJyx7fSk7cG9zaXRpb25zPVsoaXRlbVsnZ3JvdXAnXSxpdGVtWydzbG90J10pXQogIGlmIGtpbmQ9PTB4NDNhOgogICBpZiBub3QgaWRlbnRpZmllZDpyYWlzZSBWYWx1ZUVycm9yKCdJdGVtIGlzIGFscmVhZHkgdW5pZGVudGlmaWVkJykKICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hcnRpZmFjdF9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkLHJlc2V0X3ZhbHVlcwogICByZXNldF9vcHRpb25zPXJlc2V0X3ZhbHVlcyhpdGVtWyd0ZW1wbGF0ZSddLHByZXZpb3VzLmdldCgnMScsW10pKSBpZiBzdXBwb3J0ZWQoaXRlbVsndGVtcGxhdGUnXSkgZWxzZSBbXQogICBtYXRlcmlhbD1ieV91aWQuZ2V0KG1hdGVyaWFsX3VpZCkKICAgaWYgbWF0ZXJpYWwgaXMgTm9uZSBvciBzdHIobWF0ZXJpYWxbJ3RlbXBsYXRlJ10pIG5vdCBpbiBjYXRhbG9nKClbJ21hdGVyaWFscyddOnJhaXNlIFZhbHVlRXJyb3IoJ093bmVkIG9yaWdpbmFsIHJlc2V0IHNjcm9sbCByZXF1aXJlZCcpCiAgIHJlcXVpcmVfY3VycmVudChtYXRlcmlhbCk7cmVxdWlyZV91bmxvY2tlZChtYXRlcmlhbCkKICAgaWYgbWF0ZXJpYWxbJ2NvdW50J109PTE6cmVtb3ZlKGRiLG93bmVyLG1hdGVyaWFsKQogICBlbHNlOmRiLmV4ZWN1dGUoJ1VQREFURSBpbnZlbnRvcnlfaXRlbXMgU0VUIGNvdW50PWNvdW50LTEgV0hFUkUgdWlkPT8gQU5EIG93bmVyPT8nLChtYXRlcmlhbF91aWQsb3duZXIpKQogICBwb3NpdGlvbnMuYXBwZW5kKChtYXRlcmlhbFsnZ3JvdXAnXSxtYXRlcmlhbFsnc2xvdCddKSk7dXBkYXRlZD17KipwcmV2aW91cywnMSc6cmVzZXRfb3B0aW9uc307ZmxhZz1GYWxzZQogIGVsc2U6CiAgIGlmIGlkZW50aWZpZWQ6cmFpc2UgVmFsdWVFcnJvcignSWRlbnRpZnkgcmVxdWlyZXMgYW4gdW5pZGVudGlmaWVkIGl0ZW0sIG5vdCBhIGZyZWUgcmVyb2xsJykKICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hcnRpZmFjdF9pZGVudGlmaWNhdGlvbiBpbXBvcnQgc3VwcG9ydGVkLGlkZW50aWZ5X3ZhbHVlcwogICB1cGRhdGVkPXsqKnByZXZpb3VzLCcxJzphY3Rpdml0eV9kcmF3KHJhbmRiZWxvdykgaWYgYWN0aXZpdHkgZWxzZSBhY2Nlc3NvcnlfZHJhdyhyYW5kYmVsb3csaXRlbVsndGVtcGxhdGUnXSkgaWYgYWNjZXNzb3J5IGVsc2UgaWRlbnRpZnlfdmFsdWVzKGl0ZW1bJ3RlbXBsYXRlJ10scHJldmlvdXMuZ2V0KCcxJyxbXSkscmFuZGJlbG93KSBpZiBzdXBwb3J0ZWQoaXRlbVsndGVtcGxhdGUnXSkgZWxzZSBkcmF3X2luaXRpYWwoaXRlbVsndGVtcGxhdGUnXSxyYW5kYmVsb3cpfTtmbGFnPVRydWUKICBpZiBraW5kPT0weDQzOCBhbmQgaXRlbVsndGVtcGxhdGUnXSBpbiAoMTY4OTE1LDE2ODkxNiwxNjg5MTcsMTY4OTE4KSBhbmQgbm90IHByZXZpb3VzLmdldCgnMzEnKToKICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5hcnRpZmFjdF9jb252ZXJzaW9uIGltcG9ydCBkcmF3IGFzIGNvbnZlcnNpb25fZHJhdwogICB1cGRhdGVkWyczMSddPWNvbnZlcnNpb25fZHJhdyhbMCwwLDBdLHt9LHJhbmRiZWxvdykKICByZXBsYWNlX2lkZW50aWZpZWQoZGIsb3duZXIsdWlkLGlkZW50aWZpZWQsZmxhZyk7cmVwbGFjZV9vcHRpb25zKGRiLG93bmVyLHVpZCxwcmV2aW91cyx1cGRhdGVkKQogIGFmdGVyPWxvYWRfaXRlbXMoZGIsb3duZXIpO2N1cnJlbnQ9eyhpWydncm91cCddLGlbJ3Nsb3QnXSk6aSBmb3IgaSBpbiBhZnRlcn0KICB3aXJlPWFja25vd2xlZGdlbWVudChraW5kLGVkLFsocCxjdXJyZW50LmdldChwKSkgZm9yIHAgaW4gcG9zaXRpb25zXSkKICBldmVudD1FdmVudCgweDIwMSxraW5kPWtpbmQrMSxwYXlsb2FkPXdpcmUpCiAgZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQKICBlbmNvZGVfZXZlbnQoZXZlbnQpCiAgaWYgcHJlcGFyZSBpcyBub3QgTm9uZTpwcmVwYXJlKCkKICBfY29tbWl0KGRiLG9wZXJhdGlvbixkaWdlc3Qsb3duZXIsa2luZCxwb3NpdGlvbnMsYmVmb3JlLGFmdGVyKQogIHJldHVybiBbZXZlbnRdCg=='}, 'els_server/storage/fixed_cubes.py': {'size': 8973, 'sha256': 'eac5378c76e116cdfe6c004b78e32edc509a6a7da437b925fc4d30d8bce60880', 'base64': 'IiIiQ29uc3VtZSBvbmUgb3duZWQgZml4ZWQgY3ViZSBhbmQgZGVsaXZlciBpdHMgb3JpZ2luYWwgY29udGVudHMgYXRvbWljYWxseS4iIiIKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuaXRlbV9hY3RvciBpbXBvcnQgcmVxdWlyZV9hY3RpdmVfY2hhcmFjdGVyCmltcG9ydCBzZWNyZXRzLHNxbGl0ZTMsc3RydWN0CmZyb20gY29udGV4dGxpYiBpbXBvcnQgY2xvc2luZwpmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmN1YmVzIGltcG9ydCBjYXRhbG9nCmZyb20gZWxzX3NlcnZlci5kb21haW4uaW52ZW50b3J5X2l0ZW1zIGltcG9ydCBWRVJJRklFRF9URU1QTEFURVMsVEVNUExBVEVfQkFHX0dST1VQUwpmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLml0ZW1fZXhwaXJhdGlvbiBpbXBvcnQgcmVxdWlyZV9jdXJyZW50CmZyb20gZWxzX3NlcnZlci5kb21haW4uaXRlbV9sb2NrcyBpbXBvcnQgcmVxdWlyZV91bmxvY2tlZApmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wuaWNlX21lc3NhZ2VzIGltcG9ydCB1c2VfcmVxdWVzdApmcm9tIGVsc19zZXJ2ZXIucHJvdG9jb2wuY3ViZV9tZXNzYWdlcyBpbXBvcnQgcmVzdWx0CmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmludmVudG9yeV9zdGF0ZSBpbXBvcnQgbG9hZF9pdGVtcyxncmFudF9pdGVtcwpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5pbnZlbnRvcnlfYWN0aW9ucyBpbXBvcnQgX2lkZW50aXR5LF9wcmV2aW91cyxfY29tbWl0CmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmludmVudG9yeV9tYW5hZ2VtZW50IGltcG9ydCBfdXBkYXRlcwpmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5ucGNfdHJhZGUgaW1wb3J0IGJhbGFuY2VzCmZyb20gZWxzX3NlcnZlci5zdG9yYWdlLml0ZW1faW5zdGFuY2VzIGltcG9ydCByZW1vdmUKZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuZXF1aXBtZW50X3JlY2VpcHRfc3RhdGUgaW1wb3J0IGN1cnJlbnRfY2hhbmdlcwoKCmRlZiBfbGVnYWN5X2FjdG9yKGRiLG93bmVyLGFjY291bnRfaWQscHJlcGFyZSk6CiAgICBpZiBub3QgY2FsbGFibGUocHJlcGFyZSk6cmFpc2UgVmFsdWVFcnJvcignTGVnYWN5IGN1YmUgY3VycmVudCBzZWxlY3RlZCBhY3RvciBjYWxsYmFjayByZXF1aXJlZCcpCiAgICBwcmVwYXJlKGRiKQogICAgcmVxdWlyZV9hY3RpdmVfY2hhcmFjdGVyKGRiLG93bmVyKQogICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UucHJvZmVzc2lvbl9zdGF0ZSBpbXBvcnQgcmVxdWlyZV9vd25lcgogICAgcmVxdWlyZV9vd25lcihkYixvd25lcixhY2NvdW50X2lkKQoKCmRlZiBvcGVuX2N1YmUocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbixyYW5kYmVsb3c9c2VjcmV0cy5yYW5kYmVsb3csKixhY2NvdW50X2lkPU5vbmUscHJlcGFyZT1Ob25lKToKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uam9iX3Jld2FyZF9ib3hlcyBpbXBvcnQgQk9YRVMgYXMgam9iX2JveGVzCiAgICBpZiBleHBlY3RlZF90ZW1wbGF0ZSBpbiBqb2JfYm94ZXM6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2Uuam9iX3Jld2FyZF9ib3hlcyBpbXBvcnQgb3Blbl9ib3gKICAgICAgICByZXR1cm4gb3Blbl9ib3gocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbixhY2NvdW50X2lkPWFjY291bnRfaWQscHJlcGFyZT1wcmVwYXJlKQogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGU9PTcxNTAzNjoKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS53YXJkcm9iZV90aWNrZXRfYm94IGltcG9ydCBvcGVuX2JveAogICAgICAgIHJldHVybiBvcGVuX2JveChwYXRoLG93bmVyLHBheWxvYWQsb3BlcmF0aW9uLGFjY291bnRfaWQ9YWNjb3VudF9pZCkKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4ucHVibGlzaGVkXzIwMjZfYnVuZGxlcyBpbXBvcnQgZW5hYmxlZAogICAgZGVmaW5pdGlvbj1lbmFibGVkKCkuZ2V0KGV4cGVjdGVkX3RlbXBsYXRlKQogICAgaWYgZGVmaW5pdGlvbiBpcyBub3QgTm9uZToKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5wdWJsaXNoZWRfMjAyNl9idW5kbGVzIGltcG9ydCBvcGVuX2J1bmRsZQogICAgICAgIHJldHVybiBvcGVuX2J1bmRsZShwYXRoLG93bmVyLHBheWxvYWQsb3BlcmF0aW9uLGRlZmluaXRpb249ZGVmaW5pdGlvbikKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfMjAyNl9mb3JjZV9yZXdhcmRzIGltcG9ydCBib3hlcyBhcyBmb3JjZV9ib3hlcwogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGUgaW4gZm9yY2VfYm94ZXMoKToKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5ib29zdGluZ18yMDI2X2ZvcmNlX3Jld2FyZHMgaW1wb3J0IG9wZW5fYm94CiAgICAgICAgcmV0dXJuIG9wZW5fYm94KHBhdGgsb3duZXIsZXhwZWN0ZWRfdGVtcGxhdGUscGF5bG9hZCxvcGVyYXRpb24pCiAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmJvb3N0aW5nXzIwMjZfcGFydGljaXBhdGlvbl9nZWFyIGltcG9ydCBCT1gsZW5hYmxlZCBhcyBnZWFyX2VuYWJsZWQKICAgIGlmIGV4cGVjdGVkX3RlbXBsYXRlPT1CT1ggYW5kIGdlYXJfZW5hYmxlZCgpOgogICAgICAgIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLmJvb3N0aW5nXzIwMjZfcGFydGljaXBhdGlvbl9nZWFyIGltcG9ydCBvcGVuX2dlYXIKICAgICAgICByZXR1cm4gb3Blbl9nZWFyKHBhdGgsb3duZXIscGF5bG9hZCxvcGVyYXRpb24sYWNjb3VudF9pZD1hY2NvdW50X2lkLHByZXBhcmU9cHJlcGFyZSkKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfMjAyNl9mYXNoaW9uX3Jld2FyZHMgaW1wb3J0IEJPWEVTLGVudHJpZXMgYXMgZmFzaGlvbl9lbnRyaWVzCiAgICBpZiBleHBlY3RlZF90ZW1wbGF0ZSBpbiBCT1hFUyBhbmQgZmFzaGlvbl9lbnRyaWVzKCk6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuYm9vc3RpbmdfMjAyNl9mYXNoaW9uX3Jld2FyZHMgaW1wb3J0IG9wZW5fZmFzaGlvbgogICAgICAgIHJldHVybiBvcGVuX2Zhc2hpb24ocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbikKICAgIGZyb20gZWxzX3NlcnZlci5kb21haW4uYm9vc3RpbmdfMjAyNl9uZXN0ZWRfY2FwYWNpdHkgaW1wb3J0IEJPWCBhcyBjYXBhY2l0eV9ib3gsaXRlbXMgYXMgY2FwYWNpdHlfaXRlbXMKICAgIGlmIGV4cGVjdGVkX3RlbXBsYXRlPT1jYXBhY2l0eV9ib3ggYW5kIGNhcGFjaXR5X2l0ZW1zKCk6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuYm9vc3RpbmdfMjAyNl9uZXN0ZWRfY2FwYWNpdHkgaW1wb3J0IG9wZW5fYm94CiAgICAgICAgcmV0dXJuIG9wZW5fYm94KHBhdGgsb3duZXIscGF5bG9hZCxvcGVyYXRpb24pCiAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmJvb3N0aW5nXzIwMjZfdGl0bGVfcmV3YXJkcyBpbXBvcnQgQk9YIGFzIHRpdGxlX2JveCxlbmFibGVkIGFzIHRpdGxlX2VuYWJsZWQKICAgIGlmIGV4cGVjdGVkX3RlbXBsYXRlPT10aXRsZV9ib3ggYW5kIHRpdGxlX2VuYWJsZWQoKToKICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuc3RvcmFnZS5ib29zdGluZ18yMDI2X3RpdGxlX3Jld2FyZHMgaW1wb3J0IG9wZW5fYm94CiAgICAgICAgcmV0dXJuIG9wZW5fYm94KHBhdGgsb3duZXIsZXhwZWN0ZWRfdGVtcGxhdGUscGF5bG9hZCxvcGVyYXRpb24pCiAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLmJvb3N0aW5nXzIwMjZfYWNjZXNzb3JpZXMgaW1wb3J0IGJveGVzIGFzIGFjY2Vzc29yeV9ib3hlcwogICAgaWYgZXhwZWN0ZWRfdGVtcGxhdGUgaW4gYWNjZXNzb3J5X2JveGVzKCk6CiAgICAgICAgZnJvbSBlbHNfc2VydmVyLnN0b3JhZ2UuYm9vc3RpbmdfMjAyNl9hY2Nlc3NvcmllcyBpbXBvcnQgb3Blbl9ib3gKICAgICAgICByZXR1cm4gb3Blbl9ib3gocGF0aCxvd25lcixleHBlY3RlZF90ZW1wbGF0ZSxwYXlsb2FkLG9wZXJhdGlvbikKICAgIHJlcXVlc3Q9dXNlX3JlcXVlc3QocGF5bG9hZCkKICAgIGlmIChhbnkodiBub3QgaW4gKDAsMSkgZm9yIHYgaW4gKHJlcXVlc3QuZmxhZzEscmVxdWVzdC5mbGFnMixyZXF1ZXN0LmZsYWczKSkKICAgICAgICBvciBleHBlY3RlZF90ZW1wbGF0ZSBub3QgaW4gY2F0YWxvZygpKTpyYWlzZSBWYWx1ZUVycm9yKCdVbnN1cHBvcnRlZCBmaXhlZCBjdWJlIHVzZScpCiAgICByb3c9Y2F0YWxvZygpW2V4cGVjdGVkX3RlbXBsYXRlXQogICAgIyBOYXRpdmUgc2VsZWN0aW9uIHF1YW50aXR5IFVJIHNlbmRzIENvdW50IGFzIHRoZSBmaW5hbCByZXF1ZXN0IG9wdGlvbi4KICAgICMgWmVybyBpcyB0aGUgaGlzdG9yaWNhbCBvbmUtYm94IHJvdXRlOyBvbmUgZXhwbGljaXRseSByZXF1ZXN0cyBvbmUgYm94LgogICAgIyBCdWxrIGNvdW50cyByZW1haW4gdW5zdXBwb3J0ZWQ6IG5ldmVyIGNvbnN1bWUgb25lIGZvciBhIGxhcmdlciByZXF1ZXN0LgogICAgaWYgcmVxdWVzdC5vcHRpb24hPTAgYW5kIG5vdChyZXF1ZXN0Lm9wdGlvbj09MSBhbmQgcm93WydzZWxlY3Rpb25fY291bnQnXT09MSk6CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignVW5zdXBwb3J0ZWQgZml4ZWQgY3ViZSBxdWFudGl0eScpCiAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLnJlZ2lvbmFsX2Jvc3NfY3ViZXNfbGVnYWN5IGltcG9ydCBCT1hFUyxwb29sX2ZvcgogICAgbGVnYWN5PWV4cGVjdGVkX3RlbXBsYXRlIGluIEJPWEVTCiAgICBncm93aW5nPShleHBlY3RlZF90ZW1wbGF0ZT09MTY4ODg5IGFuZCByb3cuZ2V0KCdncm93aW5nX2FkdmVudHVyZV9raXQnKWlzIFRydWUpCiAgICBpZiByb3dbJ3NlbGVjdGlvbl9jb3VudCddOgogICAgICAgIGlmIGxlbihyZXF1ZXN0LmNob2ljZXMpIT0xOnJhaXNlIFZhbHVlRXJyb3IoJ1NlbGVjdCBleGFjdGx5IG9uZSBuYXRpdmUgY3ViZSBpdGVtJykKICAgICAgICBvdXRwdXQ9bmV4dCgoZSBmb3IgZSBpbiByb3dbJ2VudHJpZXMnXSBpZiBlWyd0ZW1wbGF0ZSddPT1yZXF1ZXN0LmNob2ljZXNbMF0pLE5vbmUpCiAgICAgICAgaWYgb3V0cHV0IGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignQ2hvaWNlIGlzIG91dHNpZGUgdGhpcyBjdWJlJykKICAgIGVsc2U6CiAgICAgICAgaWYgcmVxdWVzdC5jaG9pY2VzOnJhaXNlIFZhbHVlRXJyb3IoJ0ZpeGVkIGN1YmUgZG9lcyBub3QgYWNjZXB0IGEgY2hvaWNlJykKICAgICAgICBvdXRwdXQ9Tm9uZSBpZiByb3cuZ2V0KCdyYW5kb20nKW9yIGdyb3dpbmcgZWxzZSByb3dbJ2VudHJpZXMnXVswXQogICAgb3duZXIsZGlnZXN0PV9pZGVudGl0eShvd25lciwweDE5NixzdHJ1Y3QucGFjaygnPmknLGV4cGVjdGVkX3RlbXBsYXRlKStwYXlsb2FkLG9wZXJhdGlvbikKICAgIHdpdGggY2xvc2luZyhzcWxpdGUzLmNvbm5lY3QocGF0aCx0aW1lb3V0PTEwKSkgYXMgZGIsZGI6CiAgICAgICAgZGIuZXhlY3V0ZSgnUFJBR01BIGZvcmVpZ25fa2V5cz1PTicpO2RiLmV4ZWN1dGUoJ0JFR0lOIElNTUVESUFURScpO3JlcXVpcmVfYWN0aXZlX2NoYXJhY3RlcihkYixvd25lcikKICAgICAgICBpZiBsZWdhY3k6X2xlZ2FjeV9hY3RvcihkYixvd25lcixhY2NvdW50X2lkLHByZXBhcmUpCiAgICAgICAgaWYgZ3Jvd2luZzoKICAgICAgICAgICAgZnJvbSBlbHNfc2VydmVyLmRvbWFpbi5ncm93aW5nX2FkdmVudHVyZV9raXQgaW1wb3J0IG91dHB1dHNfZm9yCiAgICAgICAgICAgIHJvbGU9ZGIuZXhlY3V0ZSgnU0VMRUNUIHVuaXRfY2xhc3MgRlJPTSBjaGFyYWN0ZXJzIFdIRVJFIHVpZD0/Jywob3duZXIsKSkuZmV0Y2hvbmUoKQogICAgICAgICAgICBpZiByb2xlIGlzIE5vbmU6cmFpc2UgVmFsdWVFcnJvcignR3Jvd2luZyBraXQgb3duZXIgbWlzc2luZycpCiAgICAgICAgICAgIGtpdF9vdXRwdXRzPW91dHB1dHNfZm9yKHJvbGVbMF0pCiAgICAgICAgb2xkPV9wcmV2aW91cyhkYixvcGVyYXRpb24sZGlnZXN0KTtiZWZvcmU9bG9hZF9pdGVtcyhkYixvd25lcik7YmFsYW5jZT1iYWxhbmNlcyhkYixvd25lcikKICAgICAgICBpZiBvbGQgaXMgbm90IE5vbmU6CiAgICAgICAgICAgIGV2ZW50cz1fdXBkYXRlcyhjdXJyZW50X2NoYW5nZXMoZGIsb3BlcmF0aW9uLG93bmVyLDB4MTk2LG9sZCxiZWZvcmUpKStyZXN1bHQoYmFsYW5jZVsnZWQnXSkKICAgICAgICAgICAgaWYgbGVnYWN5OgogICAgICAgICAgICAgICAgZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQKICAgICAgICAgICAgICAgIGZvciBldmVudCBpbiBldmVudHM6ZW5jb2RlX2V2ZW50KGV2ZW50KQogICAgICAgICAgICAgICAgX2xlZ2FjeV9hY3RvcihkYixvd25lcixhY2NvdW50X2lkLHByZXBhcmUpCiAgICAgICAgICAgIHJldHVybiBldmVudHMKICAgICAgICBpZiBleHBlY3RlZF90ZW1wbGF0ZT09NzIyNTMxOnJhaXNlIFZhbHVlRXJyb3IoJ1NlbGVjdGlvbjcyMjUzMSBuZXcgb3BlcmF0aW9ucyBwYXVzZWQgaW4gcmVhZGVyLXByZXNlcnZpbmcgQ291bnQxIHJlY292ZXJ5JykKICAgICAgICBpdGVtPW5leHQoKGkgZm9yIGkgaW4gYmVmb3JlIGlmIGlbJ3VpZCddPT1yZXF1ZXN0LnVpZCksTm9uZSkKICAgICAgICBpZiBpdGVtIGlzIE5vbmUgb3IgaXRlbVsndGVtcGxhdGUnXSE9ZXhwZWN0ZWRfdGVtcGxhdGUgb3IgaXRlbVsnZ3JvdXAnXSE9NDoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignRml4ZWQgY3ViZSBkb2VzIG5vdCBtYXRjaCBvd25lZCBwcmV2aWV3ZWQgaW5zdGFuY2UnKQogICAgICAgIHJlcXVpcmVfY3VycmVudChpdGVtKTtyZXF1aXJlX3VubG9ja2VkKGl0ZW0pCiAgICAgICAgaWYgYmFsYW5jZVsncmV2aXNpb24nXT49MioqNjMtMTpyYWlzZSBWYWx1ZUVycm9yKCdGaXhlZCBjdWJlIHJldmlzaW9uIG92ZXJmbG93JykKICAgICAgICBpZiBsZWdhY3k6CiAgICAgICAgICAgIHJvbGU9ZGIuZXhlY3V0ZSgnU0VMRUNUIHVuaXRfdHlwZSx1bml0X2NsYXNzIEZST00gY2hhcmFjdGVycyBXSEVSRSB1aWQ9PycsKG93bmVyLCkpLmZldGNob25lKCkKICAgICAgICAgICAgaWYgcm9sZSBpcyBOb25lOnJhaXNlIFZhbHVlRXJyb3IoJ0xlZ2FjeSBjdWJlIG93bmVyIG1pc3NpbmcnKQogICAgICAgICAgICByb3c9cG9vbF9mb3Iocm93LCpyb2xlKQogICAgICAgIGlmIHJvdy5nZXQoJ3JhbmRvbScpOgogICAgICAgICAgICBmcm9tIGVsc19zZXJ2ZXIuZG9tYWluLnJlZ2lvbmFsX2Jvc3NfY3ViZXMgaW1wb3J0IGRyYXcKICAgICAgICAgICAgb3V0cHV0PWRyYXcocm93LHJhbmRiZWxvdygxMDAwMCkpCiAgICAgICAgcmVnaW9uYWxfc291cmNlPU5vbmUKICAgICAgICBpZiBsZWdhY3k6CiAgICAgICAgICAgIGZyb20gZWxzX3NlcnZlci5zdG9yYWdlLnJlZ2lvbmFsX2Jvc3NfY3ViZV9zb3VyY2UgaW1wb3J0IF9Pd25lZEN1YmVTb3VyY2UKICAgICAgICAgICAgcmVnaW9uYWxfc291cmNlPV9Pd25lZEN1YmVTb3VyY2UoZGIsb3duZXIsaXRlbSxvdXRwdXQpCiAgICAgICAgc291cmNlPShpdGVtWydncm91cCddLGl0ZW1bJ3Nsb3QnXSkKICAgICAgICBpZiBpdGVtWydjb3VudCddPT0xOnJlbW92ZShkYixvd25lcixpdGVtKQogICAgICAgIGVsc2U6ZGIuZXhlY3V0ZSgnVVBEQVRFIGludmVudG9yeV9pdGVtcyBTRVQgY291bnQ9Y291bnQtMSBXSEVSRSB1aWQ9PyBBTkQgb3duZXI9PycsKGl0ZW1bJ3VpZCddLG93bmVyKSkKICAgICAgICBpZiByZWdpb25hbF9zb3VyY2UgaXMgbm90IE5vbmU6cmVnaW9uYWxfc291cmNlLmRlYml0X2NvbXBsZXRlKCkKICAgICAgICBvdXRwdXRzPWtpdF9vdXRwdXRzIGlmIGdyb3dpbmcgZWxzZShvdXRwdXQsKQogICAgICAgIHBsYW49W10KICAgICAgICBmb3Igc2VsZWN0ZWQgaW4gb3V0cHV0czoKICAgICAgICAgICAgcXVhbnRpdHk9c2VsZWN0ZWRbJ3F1YW50aXR5J10KICAgICAgICAgICAgd2hpbGUgcXVhbnRpdHk6CiAgICAgICAgICAgICAgICBkZWx0YT1taW4ocXVhbnRpdHksOTkpO3F1YW50aXR5LT1kZWx0YQogICAgICAgICAgICAgICAgcGxhbi5hcHBlbmQoZGljdCh0ZW1wbGF0ZT1zZWxlY3RlZFsndGVtcGxhdGUnXSxtZXRhZGF0YT1WRVJJRklFRF9URU1QTEFURVNbc2VsZWN0ZWRbJ3RlbXBsYXRlJ11dLAogICAgICAgICAgICAgICAgICAgIGdyb3VwPVRFTVBMQVRFX0JBR19HUk9VUFNbc2VsZWN0ZWRbJ3RlbXBsYXRlJ11dLHF1YW50aXR5PWRlbHRhKSkKICAgICAgICAgICAgICAgIGlmIGdyb3dpbmc6cGxhblstMV1bJ2VuaGFuY2VtZW50J109c2VsZWN0ZWRbJ2VuaGFuY2VtZW50J10KICAgICAgICBncmFudHM9Z3JhbnRfaXRlbXMoZGIscGxhbixvd25lcixyZWdpb25hbF9jdWJlX3NvdXJjZT1yZWdpb25hbF9zb3VyY2UpCiAgICAgICAgYWZ0ZXI9bG9hZF9pdGVtcyhkYixvd25lcik7Y3VycmVudD17KGlbJ2dyb3VwJ10saVsnc2xvdCddKTppIGZvciBpIGluIGFmdGVyfQogICAgICAgIHBvc2l0aW9ucz1zb3J0ZWQoe3NvdXJjZSwqWyhpWydncm91cCddLGlbJ3Nsb3QnXSkgZm9yIGkgaW4gZ3JhbnRzXX0pCiAgICAgICAgZXZlbnRzPXJlc3VsdChiYWxhbmNlWydlZCddLFsocCxjdXJyZW50LmdldChwKSkgZm9yIHAgaW4gcG9zaXRpb25zXSxbKHNlbGVjdGVkWyd0ZW1wbGF0ZSddLHNlbGVjdGVkWydxdWFudGl0eSddKWZvciBzZWxlY3RlZCBpbiBvdXRwdXRzXSkKICAgICAgICBpZiBncm93aW5nIG9yIGxlZ2FjeToKICAgICAgICAgICAgZnJvbSBlbHNfc2VydmVyLnByb3RvY29sLnByb3RvY29sX2NvZGVjIGltcG9ydCBlbmNvZGVfZXZlbnQKICAgICAgICAgICAgZm9yIGV2ZW50IGluIGV2ZW50czplbmNvZGVfZXZlbnQoZXZlbnQpCiAgICAgICAgZGIuZXhlY3V0ZSgnVVBEQVRFIHJld2FyZF9iYWxhbmNlcyBTRVQgcmV2aXNpb249cmV2aXNpb24rMSBXSEVSRSB1aWQ9PycsKG93bmVyLCkpCiAgICAgICAgX2NvbW1pdChkYixvcGVyYXRpb24sZGlnZXN0LG93bmVyLDB4MTk2LHBvc2l0aW9ucyxiZWZvcmUsYWZ0ZXIpCiAgICAgICAgaWYgbGVnYWN5Ol9sZWdhY3lfYWN0b3IoZGIsb3duZXIsYWNjb3VudF9pZCxwcmVwYXJlKQogICAgICAgIHJldHVybiBldmVudHMK'}}

def repair_guard_payloads():
    import base64
    expected = {'els_server/storage/relationships.py','els_server/storage/couple_closures.py','els_server/storage/identification_ui.py','els_server/storage/fixed_cubes.py'}
    need(isinstance(REPAIR_RECOVERY_GUARD_PAYLOADS,dict) and set(REPAIR_RECOVERY_GUARD_PAYLOADS)==expected,
         'Exact four Repair recovery guard bindings pending')
    result={}
    for name,row in REPAIR_RECOVERY_GUARD_PAYLOADS.items():
        raw=base64.b64decode(row['base64'],validate=True)
        need(len(raw)==row['size'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'Repair guard byte binding differs')
        result[name]=raw
    return result

def repair_database_paths(workspace):
    return [workspace/'state/integrated.sqlite3',workspace/'state/friends/accounts.sqlite3']

def repair_database_state(workspace):
    result={}
    for path in repair_database_paths(workspace):
        no_links(path)
        result[str(path)]={'exists':path.exists(),'typed_sha256':managed_database_snapshot(path)if path.exists()else None}
    return result

def repair_writer_barriers(root,workspace,stack):
    # Both original SaveLease paths are held even for absent stores. SQLite is
    # opened only for an existing store; observation never creates a player DB.
    import sqlite3
    from contextlib import closing
    ns={};exec(compile((root/'els_server/storage/lifecycle.py').read_bytes(),'<installed Repair recovery SaveLease>','exec'),ns)
    for path in repair_database_paths(workspace):
        no_links(path);stack.enter_context(ns['SaveLease'](path))
        if path.exists():
            connection=stack.enter_context(closing(sqlite3.connect(path,timeout=3)))
            connection.execute('BEGIN IMMEDIATE');stack.callback(connection.rollback)

def repair_original_restore_allowed(j,current_state):
    # Missing/old journal fields are not an authorization to restore old code.
    before=j.get('repair_database_before')
    return(j.get('repair_recovery_schema')==1 and j.get('repair_writer_admission_opened')is False
           and j.get('repair_guarded_candidate')is None
           and isinstance(before,dict) and len(before)==2 and before==current_state)

def repair_guarded_documents(workspace,metadata,commit,new_rows,formal,additions,token):
    need(re.fullmatch('[a-f0-9]{32}',token or '')is not None,'Invalid Repair recovery token')
    need(len(new_rows)==1800 and len(formal)==1342,'Recovery requires the complete signedLOCAL/C3 source')
    docs,installed,pointer=generated_documents(workspace,metadata,commit,new_rows,formal,additions)
    guarded=metadata['release']+'-guarded-'+token[:12]
    guards=repair_guard_payloads()
    for name,raw in guards.items():
        need(name in formal and name in installed,'Guard is not a complete C3 source member')
        installed[name]={'path':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    marker=json.loads(docs['local-first-run.json']);marker['release']=guarded
    docs['local-first-run.json']=encoded(marker)
    installed['local-first-run.json']={'path':'local-first-run.json','size':len(docs['local-first-run.json']),'sha256':hashlib.sha256(docs['local-first-run.json']).hexdigest()}
    flags=dict(recovery_only=True,compatible_read_only=False,complete_C3_reader_and_data=True,all_three_guards=True,
               selection_reader_compatible_recovery=True,all_five_selection_readers_retained=True,new_722531_operations_paused=True,
               original_parent_code=False,player_database_restore=False,guarded_paths=sorted(guards),
               source_binding_sha256=REPAIR_SOURCE_SET,source_business_files=1342)
    business=json.loads(docs['local-business-manifest.json']);business.update(flags,release=guarded,
        files=[installed[name]for name in sorted(set(formal)|additions)])
    docs['local-business-manifest.json']=encoded(business)
    business_hash=hashlib.sha256(docs['local-business-manifest.json']).hexdigest()
    docs['client-bundle-manifest.json']=encoded(dict(release=guarded,channel='local',files=[installed[name]for name in sorted(installed)],**flags))
    docs['release-snapshot.json']=encoded(dict(release=guarded,channel='local',status='Repair-compatible-guarded-recovery-only',
        repository_commit=commit,local_business_manifest_sha256=business_hash,fresh_save_imported=False,**flags))
    pointer.update(flags,release=guarded,path='releases/local/'+guarded,manifest_sha256=business_hash,
        verified=False,first_initialization=False,recovery_of=metadata['release'],recovery_observation_complete=False)
    need(len(installed)==1802,'Signed LOCAL recovery must retain generated config and marker')
    return docs,installed,pointer,guards

def repair_guarded_tree(runtime,workspace,metadata,new_rows,formal,additions,j,u):
    commit=(j.get('candidate')or{}).get('repository_commit')or j['target']
    docs,installed,pointer,guards=repair_guarded_documents(workspace,metadata,commit,new_rows,formal,additions,j['token'])
    target=under(workspace,pointer['path'])
    if not target.exists():
        need(shutil.disk_usage(workspace).free>sum(r['size']for r in installed.values())+512*1024*1024,'Insufficient space for complete compatible recovery')
        stage=Path(tempfile.mkdtemp(prefix='.repair-guarded-',dir=target.parent))
        j['repair_guard_stage']=str(stage);u.atomic(Path(j['journal']),j)
        for name,row in new_rows.items():
            verify(runtime,row);dst=under(stage,name);dst.parent.mkdir(parents=True,exist_ok=True)
            if name in guards:write_new(dst,guards[name])
            else:shutil.copyfile(under(runtime,name),dst)
        for name,raw in docs.items():
            dst=under(stage,name);dst.parent.mkdir(parents=True,exist_ok=True);write_new(dst,raw)
        managed_verify_tree(stage,installed,docs)
        need(not target.exists(),'Recovery target appeared');stage.rename(target)
    managed_verify_tree(target,installed,docs)
    return target,pointer,docs,installed

def repair_stop_writers(workspace,j,u,psutil,old,target):
    # A restart can create its Popen and fail before returning its identity.
    # Discover only canonical, exact installed roots through the mature normal
    # stop contract; unknown argv, a foreign listener or a live lease refuses.
    op=Path(j['journal']).parent
    roots=[old['root']]
    if target.exists()and target not in roots:roots.append(target)
    if j.get('repair_guarded_candidate'):
        root=under(workspace,j['repair_guarded_candidate']['path'])
        if root.exists()and root not in roots:roots.append(root)
    for index,root in enumerate(roots):
        stop=op/('repair-stop-'+str(index)+'-'+uuid.uuid4().hex);stop.mkdir()
        u.stop_owned(root,workspace,psutil,stop)
    doc,_,_=u.config_paths(old['root'],workspace);u.port_idle(doc['port']);u.idle(psutil)

def repair_settle_failure(runtime,workspace,metadata,new_rows,formal,additions,j,old,u,psutil,old_service,
                          observation_seconds=120,interrupted=False,fault=None):
    from contextlib import ExitStack
    current_path=workspace/'releases/local/current.json';current=read(current_path)
    allowed=[j['parent']]+[p for p in(j.get('candidate'),j.get('repair_guarded_candidate'))if p is not None]
    need(current in allowed,'Foreign current prevents Repair recovery; no code or DB restored')
    j['repair_safe_to_release']=False;u.atomic(Path(j['journal']),j)
    target=under(workspace,(j.get('candidate')or{'path':'releases/local/'+metadata['release']})['path'])
    repair_stop_writers(workspace,j,u,psutil,old,target)
    with ExitStack()as stack:
        repair_writer_barriers(old['root'],workspace,stack)
        state=None
        try:state=repair_database_state(workspace)
        except BaseException:pass # No readable two-store proof means never choose old code.
        if repair_original_restore_allowed(j,state):
            need(read(current_path)==current,'Current moved during parent recovery admission')
            u.atomic(current_path,old['pointer'])
            j.update(phase='interrupted-code-restored'if interrupted else'code-restored',repair_recovery_mode='exact-parent-before-new-writer',repair_safe_to_release=False)
            u.atomic(Path(j['journal']),j)
            area=Path(j['journal']).parent/('parent-observation-'+uuid.uuid4().hex);area.mkdir()
            _,_,save=u.config_paths(old['root'],workspace)
            j['repair_parent_observation']=u.smoke(old['root'],save,area,observation_seconds)
            need(repair_database_state(workspace)==state,'Original DB changed during parent recovery observation')
            managed_verify_tree(old['root'],old['installed'],old['documents'])
        else:
            guarded,pointer,docs,installed=repair_guarded_tree(runtime,workspace,metadata,new_rows,formal,additions,j,u)
            need(read(current_path)==current,'Current moved during guarded recovery admission')
            j['repair_guarded_candidate']=pointer;j['phase']='guarded-ready';u.atomic(Path(j['journal']),j)
            u.atomic(current_path,pointer);j['phase']='guarded-promoted';u.atomic(Path(j['journal']),j)
            # A failure after this point deliberately leaves full C3 plus all
            # three guards selected. Never fall through to the old pointer.
            need(state is not None,'Guarded reader retained; original DB integrity requires review')
            if fault:fault('after-guarded-promotion')
            area=Path(j['journal']).parent/('guarded-observation-'+uuid.uuid4().hex);area.mkdir()
            _,_,save=u.config_paths(guarded,workspace)
            proof=u.smoke(guarded,save,area,observation_seconds)
            need(repair_database_state(workspace)==state,'Original DB changed during guarded observation')
            managed_verify_tree(guarded,installed,docs);need(read(current_path)==pointer,'Guarded pointer changed')
            # Keep the pointer byte-stable for repeated recovery; qualification
            # lives in the separate journal/receipt, not an invented acceptance.
            j.update(phase='guarded-code-preserved',repair_recovery_mode='complete-nine-leaf-four-guards',
                     repair_guarded_observation=proof,repair_safe_to_release=False)
            u.atomic(Path(j['journal']),j)
            u.atomic(Path(j['journal']).parent/'repair-recovery.json',dict(ok=True,guarded=True,root=str(guarded),pointer=pointer,
                observation=proof,original_databases_preserved=True,player_database_restore=False,original_parent_code=False))
            j['repair_safe_to_release']=True;u.atomic(Path(j['journal']),j)
            return 'guarded'
    # Restart the exact original service only after the proven unchanged-store
    # branch and after releasing its SaveLease/SQL barriers.
    restarted=u.restart(old['root'],workspace,old_service,Path(j['journal']).parent)
    repair_require_service_ready(restarted,old['root'],workspace,u,psutil)
    j['repair_safe_to_release']=True;u.atomic(Path(j['journal']),j)
    return 'parent'

def repair_require_service_ready(restarted,root,workspace,u,psutil):
    if not restarted:return
    import socket,time
    doc,_,_=u.config_paths(root,workspace);deadline=time.monotonic()+45
    while True:
        need(psutil.pid_exists(restarted['pid'])and time.monotonic()<deadline,'Recovered original service is not ready')
        try:
            with socket.create_connection(('127.0.0.1',doc['port']),timeout=1)as connection:
                need(bool(connection.recv(64)),'Recovered original service is not ready')
            return
        except OSError:time.sleep(.25)

def repair_publication_locks(workspace,j,u):
    from contextlib import contextmanager
    @contextmanager
    def hold():
        paths=[workspace/'analysis/coordination-20261015'/n for n in('active-publication.lock','publication-record.lock')]
        identity=dict(schema=u.SCHEMA,token=j['token'],pid=os.getpid(),created=j['created'],operation='local-oneclick-updater',journal=j['journal'])
        held={};admitted=False
        try:
            for path in paths:
                no_links(path);path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('x',encoding='utf8')as f:json.dump(identity,f);f.flush();os.fsync(f.fileno())
                held[path]=path.stat().st_ino
            admitted=True;yield
        finally:
            if admitted and j.get('repair_safe_to_release')is True:
                need(read(no_links(Path(j['journal'])))==j and j.get('phase')in('complete','guarded-code-preserved','code-restored','interrupted-code-restored'),
                     'Repair release admission was not durably committed; publication locks retained')
            if not admitted or j.get('repair_safe_to_release')is True:
                for path,inode in held.items():
                    need(path.stat().st_ino==inode and read(path)==identity,'Repair recovery lock owner changed');path.unlink()
    return hold()

def repair_recovery_owner(workspace):
    # The Windows byte-range lock is released by the OS on process death. Its
    # persistent file is not a stale-lock authority and is never unlinked.
    from contextlib import contextmanager
    import msvcrt
    @contextmanager
    def hold():
        path=no_links(workspace/'state/local-updater/repair-recovery-owner.lock')
        path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_BINARY,0o600)
        locked=False
        try:
            with os.fdopen(fd,'r+b',buffering=0)as handle:
                inode=os.fstat(handle.fileno()).st_ino
                need(path.stat().st_ino==inode and path.stat().st_nlink==1,'Recovery owner lock path changed')
                handle.seek(0)
                try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1);locked=True
                except OSError:raise RuntimeError('Another Repair recovery owns the exclusive OS lock')
                try:
                    handle.seek(0);handle.write(encoded(dict(pid=os.getpid(),token=uuid.uuid4().hex)))
                    handle.truncate();os.fsync(handle.fileno())
                    need(path.stat().st_ino==inode,'Recovery owner lock replaced');yield
                    need(path.stat().st_ino==inode,'Recovery owner lock changed during recovery')
                finally:
                    if locked:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
        except BaseException:raise
    return hold()

def repair_managed_recover(runtime,workspace,metadata,new_rows,formal,additions):
    with repair_recovery_owner(workspace):
        return repair_managed_recover_owned(runtime,workspace,metadata,new_rows,formal,additions)

def repair_managed_recover_owned(runtime,workspace,metadata,new_rows,formal,additions):
    contract=managed_policy(metadata,new_rows);u=managed_updater()
    paths=[workspace/'analysis/coordination-20261015'/n for n in('active-publication.lock','publication-record.lock')]
    present=[p for p in paths if p.exists()]
    if not present:return
    inodes={p:p.stat().st_ino for p in present}
    identity=read(no_links(present[0]));need(identity.get('schema')==u.SCHEMA and identity.get('operation')=='local-oneclick-updater'
        and all(read(no_links(p))==identity for p in present),'Foreign Repair recovery lock')
    contract=structure_journal_contract(workspace,u,contract,identity['journal'])
    path,j=managed_journal(workspace,u,contract,identity['journal'])
    need(j.get('repair_recovery_schema')==1 and j['token']==identity['token']and j['created']==identity['created'],'Unknown Repair journal; preserve runtime')
    old=managed_old_state(workspace,contract,j['parent']);psutil=u.psutil_for(old['root']);u.idle(psutil)
    try:need(abs(psutil.Process(identity['pid']).create_time()-identity['created'])>.01,'Repair updater still owns this journal')
    except psutil.NoSuchProcess:pass
    if j.get('candidate'):
        _,_,expected=generated_documents(workspace,metadata,j['candidate']['repository_commit'],new_rows,formal,additions)
        need(j['candidate']==expected,'Unknown Repair normal candidate')
    if j.get('repair_guarded_candidate'):
        commit=(j.get('candidate')or{}).get('repository_commit')or j['target']
        _,_,expected,_=repair_guarded_documents(workspace,metadata,commit,new_rows,formal,additions,j['token'])
        need(j['repair_guarded_candidate']==expected,'Unknown guarded recovery pointer')
    if j['phase']=='complete':
        need(read(workspace/'releases/local/current.json')==j.get('candidate'),'Completed Repair current differs')
        docs,installed,_=generated_documents(workspace,metadata,j['candidate']['repository_commit'],new_rows,formal,additions)
        managed_verify_tree(under(workspace,j['candidate']['path']),installed,docs)
    else:
        stopped=path.parent/'stopped-service.json';old_service=read(stopped)if stopped.exists()else None
        repair_settle_failure(runtime,workspace,metadata,new_rows,formal,additions,j,old,u,psutil,old_service,interrupted=True)
    for p in present:need(p.stat().st_ino==inodes[p]and p.stat().st_nlink==1 and read(no_links(p))==identity,'Repair recovery lock changed');p.unlink()

def repair_recovery_pointer(workspace,metadata):
    p=read(workspace/'releases/local/current.json')
    return(p.get('source_release')==REPAIR_SOURCE_RELEASE and p.get('source_formal_manifest_sha256')==REPAIR_FORMAL
        and p.get('recovery_of')==metadata['release']and p.get('recovery_only')is True)


def managed_upgrade(runtime, workspace, repository, commit, metadata, new_rows, formal, additions,
                    documents, installed_rows, new_pointer, observation_seconds=120, fault=None):
    import time
    from contextlib import ExitStack
    contract = managed_policy(metadata, new_rows)
    need(contract is not None, 'Managed predecessor was not signed')
    contract = structure_select(contract, read(workspace / 'releases/local/current.json'))
    old = managed_old_state(workspace, contract)
    old_bytes = (workspace / 'releases/local/current.json').read_bytes()
    u = managed_updater()
    psutil = u.psutil_for(old['root'])
    u.idle(psutil)
    queue = workspace / 'analysis/user-issues-01a16dd4-20261024-v1/publish-queue-coordination-20261025-v1/status.json'
    need(not queue.exists() or u.read(queue).get('release_queue_open') is True, 'Managed publication queue is closed')
    doc, dbs, save = u.config_paths(old['root'], workspace)
    need(doc.get('state_file') == str(workspace / 'state/integrated.sqlite3'), 'Managed save must retain its original path')
    op = no_links(workspace / 'state/local-updater' / ('managed-' + uuid.uuid4().hex))
    op.mkdir(parents=True)
    journal_path = op / 'journal.json'
    j = dict(schema=u.SCHEMA, kind=MANAGED_KIND, policy_sha256=contract['policy_sha256'], token=uuid.uuid4().hex,
             created=psutil.Process().create_time(), journal=str(journal_path), phase='preparing', parent=old['pointer'],
             repository=str(repository), target=commit, player_database_restore=False,
             repair_recovery_schema=1, repair_writer_admission_opened=False, repair_safe_to_release=False)
    target = under(workspace / 'releases/local', metadata['release'])
    registry = workspace / ('state/local-updater/managed-structure-prepared.json' if structure_target(metadata) else 'state/local-updater/managed-identity-prepared.json')
    if target.exists():
        need(registry.is_file(), 'Existing unowned target preserved')
        registration = u.read(no_links(registry))
        prior_path, prior = managed_journal(workspace, u, contract, registration['journal'])
        need(registration.get('token') == prior['token'], 'Prepared managed target token differs')
        need(prior.get('parent') == old['pointer'] and prior.get('candidate'), 'Prepared managed target owner differs')
        recorded = prior['candidate'].get('repository_commit')
        documents, installed_rows, new_pointer = generated_documents(workspace, metadata, recorded, new_rows, formal, additions)
        need(prior['candidate'] == new_pointer, 'Prepared managed target pointer differs')
        managed_verify_tree(target, installed_rows, documents)
    u.atomic(journal_path, j)
    old_service = restarted = None
    promoted = False
    for name in ('active-publication.lock', 'publication-record.lock'):
        no_links(workspace / 'analysis/coordination-20261015' / name)
    with repair_publication_locks(workspace, j, u):
        try:
            need((workspace / 'releases/local/current.json').read_bytes() == old_bytes, 'Managed current changed before admission')
            git_unchanged(repository, commit)
            u.idle(psutil)
            old_service = u.stop_owned(old['root'], workspace, psutil, op)
            u.port_idle(doc['port'])
            with ExitStack() as stack:
                repair_writer_barriers(old['root'], workspace, stack)
                j['repair_database_before'] = repair_database_state(workspace)
                u.atomic(journal_path, j)
                before = {str(p): managed_database_snapshot(p) for p in dbs}
                original_digest = {str(p): u.dbdigest(p) for p in dbs}
                for p in dbs:
                    u.api_backup(p, op / 'backups' / p.relative_to(workspace))
                (op / 'parent-pointer.raw.json').write_bytes(old_bytes)
                u.atomic(op / 'backup.json', dict(ok=True, existing_database_count=len(dbs), SQLite_API=True,
                                                typed_full_schema_and_rows=before, player_database_restore=False))
                if fault: fault('after-backup')
                if not target.exists():
                    stage = Path(tempfile.mkdtemp(prefix='.managed-stage-', dir=target.parent))
                    j['stage'] = str(stage)
                    u.atomic(journal_path, j)
                    for row in new_rows.values():
                        src = under(runtime, row['path']); verify(runtime, row)
                        dst = under(stage, row['path']); dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(src, dst)
                    for name, data in documents.items():
                        dst = under(stage, name); dst.parent.mkdir(parents=True, exist_ok=True); write_new(dst, data)
                    managed_verify_tree(stage, installed_rows, documents)
                    j.update(phase='ready-to-promote', candidate=new_pointer)
                    u.atomic(journal_path, j); u.atomic(registry, dict(journal=str(journal_path), token=j['token']))
                    need(not target.exists(), 'Managed immutable target appeared')
                    stage.rename(target)
                else:
                    j.update(phase='ready-to-promote', candidate=new_pointer)
                    u.atomic(journal_path, j); u.atomic(registry, dict(journal=str(journal_path), token=j['token']))
                need((target / 'config/server.toml').read_bytes() == old['documents']['config/server.toml'], 'Managed configuration changed')
                managed_verify_tree(target, installed_rows, documents)
                pre = op / 'private-preflight'; pre.mkdir()
                proof = u.smoke(target, save, pre, min(3, observation_seconds))
                need(all(managed_database_snapshot(Path(p)) == v for p, v in before.items()), 'Original DB changed before promotion')
                need((workspace / 'releases/local/current.json').read_bytes() == old_bytes, 'Managed current changed before promotion')
                git_unchanged(repository, commit)
                if fault: fault('before-pointer-write')
                need((workspace / 'releases/local/current.json').read_bytes() == old_bytes, 'Managed current changed at promotion CAS')
                u.atomic(workspace / 'releases/local/current.json', new_pointer); promoted = True
                j['phase'] = 'promoted'; u.atomic(journal_path, j)
                if fault: fault('after-promotion')
                observed = op / 'private-observation'; observed.mkdir()
                proof = u.smoke(target, save, observed, observation_seconds)
                need(all(managed_database_snapshot(Path(p)) == v and u.dbdigest(Path(p)) == original_digest[p]
                         for p, v in before.items()), 'Original DB changed during managed upgrade')
                need(read(workspace / 'releases/local/current.json') == new_pointer, 'Managed current changed during observation')
                managed_verify_tree(target, installed_rows, documents)
                need(repair_database_state(workspace)==j['repair_database_before'], 'Two original stores changed before writer admission')
                j['repair_writer_admission_opened']=True
                u.atomic(journal_path,j) # Durable before either lease or SQL barrier is released.
            if fault: fault('after-writer-admission')
            restarted = u.restart(target, workspace, old_service, op)
            if fault: fault('after-new-service-restart')
            if restarted:
                import socket
                deadline = time.monotonic() + 45
                while True:
                    need(psutil.pid_exists(restarted['pid']) and time.monotonic() < deadline, 'Managed service restart failed')
                    try:
                        with socket.create_connection(('127.0.0.1', doc['port']), timeout=1) as s:
                            need(bool(s.recv(64)), 'Managed service is not ready')
                        break
                    except OSError:
                        time.sleep(.25)
            if fault: fault('before-completion')
            j['phase'] = 'complete'; u.atomic(journal_path, j)
            result = dict(ok=True, workspace=str(workspace), root=str(target), release=metadata['release'], migrated=True,
                          reused=False, existing_databases=len(dbs), observation_seconds=proof['seconds'],
                          original_typed_rows_and_schema_unchanged=True, player_database_restore=False)
            u.atomic(op / 'completion.json', result)
            j['repair_safe_to_release']=True; u.atomic(journal_path,j)
            return result
        except BaseException:
            repair_settle_failure(runtime,workspace,metadata,new_rows,formal,additions,j,old,u,psutil,old_service,
                                  observation_seconds=observation_seconds,fault=fault)
            raise


def initialize(runtime, workspace, repository, commit, runtime_manifest):
    repair_require_bindings()
    runtime, workspace, repository = map(no_links, (runtime, workspace, repository))
    need(all(path == path.resolve() for path in (runtime, workspace, repository)),
         'Noncanonical installation directories are refused')
    need(repository.is_dir() and runtime.is_dir(), 'Runtime or Git repository directory is missing')
    need(re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', commit or '') is not None, 'Invalid pinned Git commit')
    need(workspace == repository / '.runtime-cache' / 'unified-local', 'Unexpected first local workspace')
    need(Path(git(repository, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == repository.resolve(),
         'Select the Git repository root')
    git_unchanged(repository, commit)
    manifest_rows = rows(read(runtime_manifest))
    need('python/python.exe' in manifest_rows and 'local-bootstrap-source.json' in manifest_rows,
         'Signed LOCAL package entry points are missing')
    for index, (path, row) in enumerate(manifest_rows.items(), 1):
        need(not path.casefold().startswith(('state/', 'logs/', 'run/')) and
             path.casefold() not in ('config/server.toml', 'local-first-run.json', 'client-bundle-manifest.json',
                                     'local-business-manifest.json', 'release-snapshot.json'),
             'Signed source package contains machine state or generated manifests')
        need(not path.casefold().endswith(('.sqlite', '.sqlite3', '.db')) or
             path == 'els_server/data/client/catalog.sqlite3', 'Signed source package contains a player database')
        need(not path.casefold().endswith(('.pem', '.key', '.pfx', '.p12', '.env', '.sqlite3-wal', '.sqlite3-shm')),
             'Signed source package contains private machine state')
        verify(runtime, row)
        if index % 100 == 0:
            progress(2 + 10 * index // len(manifest_rows), '正在校验完整本地运行组件…')
    metadata = read(runtime / 'local-bootstrap-source.json')
    need(repair_target(metadata), 'Dedicated repair bootstrap requires exact final repair metadata')
    repair_policy(metadata,manifest_rows)
    if metadata.get('source_release') == STRUCTURE_SOURCE_RELEASE:
        structure_policy(metadata, manifest_rows)
    formal, overrides, additions = source_binding(repository, commit, runtime, manifest_rows, metadata)
    documents, installed_rows, pointer = generated_documents(workspace, metadata, commit,
                                                             manifest_rows, formal, additions)
    progress(35, '已核对签名组件与 Git 本地版本，正在准备独立安装…')
    workspace.mkdir(parents=True, exist_ok=True)
    no_links(workspace)
    with installation_lock(workspace):
        current = workspace / 'releases/local/current.json'
        if current.exists():
            repair_managed_recover(runtime, workspace, metadata, manifest_rows, formal, additions)
            need(not repair_recovery_pointer(workspace,metadata), 'Complete C3 compatible guarded recovery is retained; normal writer admission requires a separately qualified forward repair')
            if managed_is_old(workspace, metadata):
                result = managed_upgrade(runtime, workspace, repository, commit, metadata, manifest_rows, formal,
                                         additions, documents, installed_rows, pointer)
            else:
                result = check_existing(workspace, metadata, manifest_rows, documents)
            git_unchanged(repository, commit)
            return result
        releases = under(workspace, 'releases/local')
        releases.mkdir(parents=True, exist_ok=True)
        target = under(releases, metadata['release'])
        if target.exists():
            # A crash may occur after complete immutable promotion but before
            # publishing current.json. Only an exactly matching complete tree
            # can be adopted; no existing file, configuration or save is changed.
            for name, data in documents.items():
                path = under(target, name)
                need(path.is_file() and path.read_bytes() == data,
                     'An incomplete or changed local installation exists; no files were replaced')
            for row in installed_rows.values():
                verify(target, row)
            git_unchanged(repository, commit)
            atomic_new(current, encoded(pointer))
            return {'ok': True, 'workspace': str(workspace), 'root': str(target),
                    'release': metadata['release'], 'reused': True, 'recovered': True}
        stage = Path(tempfile.mkdtemp(prefix='.first-install-', dir=releases))
        try:
            for index, (path, row) in enumerate(manifest_rows.items(), 1):
                destination = under(stage, path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(under(runtime, path), destination)
                verify(stage, row)
                if index % 100 == 0:
                    progress(35 + 55 * index // len(manifest_rows), '正在安装本地运行组件…')
            for name, data in documents.items():
                write_new(stage / name, data)
            for row in installed_rows.values():
                verify(stage, row)
            git_unchanged(repository, commit)
            need(not current.exists() and not target.exists(), 'Local installation changed concurrently')
            no_links(target)
            stage.rename(target)
            # Exclusive creation never replaces a concurrently published pointer.
            atomic_new(current, encoded(pointer))
            progress(100, '本地版本初始化完成，角色与存档将在首次启动时独立生成。')
            return {'ok': True, 'workspace': str(workspace), 'root': str(target),
                    'release': metadata['release'], 'reused': False}
        finally:
            if stage.exists():
                need(stage.parent == releases and stage.name.startswith('.first-install-'), 'Unsafe cleanup target')
                no_links(stage)
                shutil.rmtree(stage)
            # A promoted immutable runtime is retained on pointer I/O failure for diagnosis.
            # No automatic cleanup ever removes an installed tree or user state.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'workspace', 'repository', 'runtime-manifest', 'result'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args(argv)
    try:
        result = initialize(args.runtime, args.workspace, args.repository, args.commit, args.runtime_manifest)
        code = 0
    except Exception as error:
        result = {'ok': False, 'error': str(error), 'player_database_imported': False}
        code = 2
    # The caller chooses a new private result path; never replace another invocation.
    write_new(args.result, encoded(result))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
