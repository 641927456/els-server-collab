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
