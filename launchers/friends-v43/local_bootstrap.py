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
OVERRIDES = {'tools/launch_client.py', 'tools/launch_friends_client.py',
             'tools/client_compatibility_profiles.json', 'tools/local_fresh_state.py'}
ADDITIONS = {'tools/local_fresh_state.py'}
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


def managed_policy(metadata, new_rows):
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
    p = metadata.get('upgrade_from')
    if not isinstance(p, dict):
        return False
    current = read(workspace / 'releases/local/current.json')
    return ((current.get('release'), current.get('source_release'), current.get('source_formal_manifest_sha256')) ==
            ('local-git-first-run-20261029-v1', 'local-native-shop-flow-20261029-v1', MANAGED_OLD_FORMAL))


def managed_upgrade(runtime, workspace, repository, commit, metadata, new_rows, formal, additions,
                    documents, installed_rows, new_pointer, observation_seconds=120, fault=None):
    import time
    from contextlib import ExitStack
    contract = managed_policy(metadata, new_rows)
    need(contract is not None, 'Managed predecessor was not signed')
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
             repository=str(repository), target=commit, player_database_restore=False)
    target = under(workspace / 'releases/local', metadata['release'])
    registry = workspace / 'state/local-updater/managed-identity-prepared.json'
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
    with u.locks(workspace, j):
        try:
            need((workspace / 'releases/local/current.json').read_bytes() == old_bytes, 'Managed current changed before admission')
            git_unchanged(repository, commit)
            u.idle(psutil)
            old_service = u.stop_owned(old['root'], workspace, psutil, op)
            u.port_idle(doc['port'])
            with ExitStack() as stack:
                u.leases(old['root'], dbs, stack)
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
            restarted = u.restart(target, workspace, old_service, op)
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
            j['phase'] = 'complete'; u.atomic(journal_path, j)
            result = dict(ok=True, workspace=str(workspace), root=str(target), release=metadata['release'], migrated=True,
                          reused=False, existing_databases=len(dbs), observation_seconds=proof['seconds'],
                          original_typed_rows_and_schema_unchanged=True, player_database_restore=False)
            u.atomic(op / 'completion.json', result)
            return result
        except BaseException:
            if restarted:
                Path(restarted['stop']).write_text(u.SCHEMA, 'utf8')
                try: psutil.Process(restarted['pid']).wait(timeout=35)
                except psutil.NoSuchProcess: pass
            if promoted:
                need(read(workspace / 'releases/local/current.json') == new_pointer, 'Foreign current prevents managed code recovery')
                u.atomic(workspace / 'releases/local/current.json', old['pointer'])
            u.restart(old['root'], workspace, old_service, op)
            j['phase'] = 'code-restored'; u.atomic(journal_path, j)
            raise


def initialize(runtime, workspace, repository, commit, runtime_manifest):
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
    formal, overrides, additions = source_binding(repository, commit, runtime, manifest_rows, metadata)
    documents, installed_rows, pointer = generated_documents(workspace, metadata, commit,
                                                             manifest_rows, formal, additions)
    progress(35, '已核对签名组件与 Git 本地版本，正在准备独立安装…')
    workspace.mkdir(parents=True, exist_ok=True)
    no_links(workspace)
    with installation_lock(workspace):
        current = workspace / 'releases/local/current.json'
        if current.exists():
            managed_recover(workspace, metadata, manifest_rows, formal, additions)
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
