"""Fault, ownership and repeatability checks for a first local installation."""
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1] / 'launchers/friends-v42'
sys.path.insert(0, str(HERE))
import local_bootstrap as bootstrap
from local_fresh_state import fresh_local_allowed


def row(path, data):
    return {'path': path, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


class Fixture:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='first-local-test-', dir=HERE)
        self.root = Path(self.temporary.name)
        self.repo, self.runtime = self.root / 'repo', self.root / 'runtime'
        self.workspace = self.repo / '.runtime-cache/unified-local'
        self.repo.mkdir()
        self.runtime.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True, capture_output=True)
        (self.repo / '.gitignore').write_text('/.runtime-cache/\n', encoding='utf8')
        self.metadata = {'schema': 1, 'release': 'local-first-test-v1', 'source_release': 'local-accepted-v1',
                         'source_formal_manifest_sha256': 'a' * 64, 'profile': 'channels/formal.json',
                         'support_overrides': [], 'support_additions': []}
        originals = {'els_server/application.py': b'# accepted business\n',
                     'tools/launch_client.py': b'# accepted shared launch\n',
                     'tools/client_compatibility_profiles.json': b'{}\n',
                     'config/server.toml': b'[server]\nhost="127.0.0.1"\nstate_file="private-host-path-not-distributed"\n',
                     'els_server/data/selected2026/local-pair.json': b'{}\n'}
        formal = []
        for name, data in originals.items():
            source = 'references/local/' + name
            file = self.repo / source
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            formal.append(dict(row(name, data), source=source))
            if name != 'config/server.toml':
                self.add_runtime(name, data)
        self.metadata['generated_config_source_sha256'] = hashlib.sha256(originals['config/server.toml']).hexdigest()
        asset = row('analysis/locked.json', b'{"locked":true}\n')
        formal.append(dict(asset, asset=asset['path']))
        self.add_runtime(asset['path'], b'{"locked":true}\n')
        for name in ('channels/formal.json', 'channels/current-engine.json', 'runtime-assets.lock.json'):
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
        self.formal = {'channels': {'local': {'files': formal}}}
        self.metadata['source_file_count'] = len(formal)
        self.metadata['source_files_sha256'] = bootstrap.source_rows_hash(bootstrap.rows({'files': formal}))
        (self.repo / 'channels/formal.json').write_bytes(bootstrap.encoded(self.formal))
        selection = {'profile': self.metadata['profile'], 'accepted': {'local': {
            'release': self.metadata['source_release'],
            'formal_manifest_sha256': self.metadata['source_formal_manifest_sha256']}}}
        (self.repo / 'channels/current-engine.json').write_bytes(bootstrap.encoded(selection))
        (self.repo / 'runtime-assets.lock.json').write_bytes(bootstrap.encoded({'files': [asset]}))
        self.add_runtime('python/python.exe', b'not executed fixture runtime\n')
        self.add_runtime('tools/local_fresh_state.py', (HERE / 'local_fresh_state.py').read_bytes())
        self.metadata['support_additions'] = [{'path': 'tools/local_fresh_state.py',
                                             'runtime_sha256': bootstrap.digest(self.runtime / 'tools/local_fresh_state.py')}]
        changed = b'# reviewed fresh shared launch\n'
        self.add_runtime('tools/launch_client.py', changed)
        self.metadata['support_overrides'] = [{'path': 'tools/launch_client.py',
                                              'source_sha256': hashlib.sha256(originals['tools/launch_client.py']).hexdigest(),
                                              'runtime_sha256': hashlib.sha256(changed).hexdigest()}]
        self.refresh_manifest()
        self.commit()

    def add_runtime(self, name, data):
        path = self.runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def refresh_manifest(self):
        self.add_runtime('local-bootstrap-source.json', bootstrap.encoded(self.metadata))
        files = [row(p.relative_to(self.runtime).as_posix(), p.read_bytes())
                 for p in sorted(self.runtime.rglob('*')) if p.is_file()]
        self.manifest = self.root / 'verified-runtime-files.json'
        self.manifest.write_bytes(bootstrap.encoded({'files': files}))

    def commit(self):
        for args in (['add', '.'], ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                    'commit', '-qm', 'fixture']):
            subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True)
        self.commit_id = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.repo).decode().strip()

    def initialize(self):
        return bootstrap.initialize(self.runtime, self.workspace, self.repo, self.commit_id, self.manifest)

    def cleanup(self):
        self.temporary.cleanup()


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()

    def tearDown(self):
        self.fixture.cleanup()

    def test_first_install_all_hashes_and_fresh_contract(self):
        f = self.fixture
        result = f.initialize()
        self.assertFalse(result['reused'])
        root = Path(result['root'])
        self.assertFalse((f.workspace / 'state').exists(), 'Installation itself must not create/import player state')
        bundle = bootstrap.rows(bootstrap.read(root / 'client-bundle-manifest.json'))
        self.assertIn('config/server.toml', bundle)
        self.assertIn('local-first-run.json', bundle)
        for entry in bundle.values():
            bootstrap.verify(root, entry)
        self.assertTrue(fresh_local_allowed(root, root / 'config/server.toml', f.workspace / 'state/integrated.sqlite3'))
        bootstrap.git_unchanged(f.repo, f.commit_id)
        business = bootstrap.rows(bootstrap.read(root / 'local-business-manifest.json'))
        self.assertIn('config/server.toml', business)
        self.assertNotIn('private-host-path-not-distributed', (root / 'config/server.toml').read_text())
        self.assertFalse((f.runtime / 'config/server.toml').exists())

    def test_generated_config_binding_is_required_and_exact(self):
        f = self.fixture
        del f.metadata['generated_config_source_sha256']
        f.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'generated local configuration binding'):
            f.initialize()
        self.assertFalse(f.workspace.exists())
        f.metadata['generated_config_source_sha256'] = 'b' * 64
        f.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'generated local configuration binding'):
            f.initialize()
        self.assertFalse(f.workspace.exists())

    def test_host_config_is_never_allowed_inside_signed_runtime(self):
        f = self.fixture
        f.add_runtime('config/server.toml', b'[server]\nstate_file="owner-state"\n')
        f.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'machine state or generated manifests'):
            f.initialize()
        self.assertFalse(f.workspace.exists())

    def test_second_install_and_existing_save_are_immutable(self):
        f = self.fixture
        first = f.initialize()
        saved = f.workspace / 'state/integrated.sqlite3'
        saved.parent.mkdir()
        saved.write_bytes(b'user saved independently')
        pointer = (f.workspace / 'releases/local/current.json').read_bytes()
        self.assertTrue(f.initialize()['reused'])
        self.assertEqual(pointer, (f.workspace / 'releases/local/current.json').read_bytes())
        self.assertEqual(saved.read_bytes(), b'user saved independently')
        root = Path(first['root'])
        self.assertFalse(fresh_local_allowed(root, root / 'config/server.toml', saved))

    def test_runtime_corruption_and_download_fragment_are_rejected(self):
        f = self.fixture
        (f.runtime / 'python/python.exe').write_bytes(b'truncated')
        with self.assertRaisesRegex(ValueError, 'SHA verification'):
            f.initialize()
        self.assertFalse(f.workspace.exists())

    def test_signed_package_missing_business_row_is_rejected(self):
        f = self.fixture
        (f.runtime / 'els_server/application.py').unlink()
        f.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'omits accepted business'):
            f.initialize()
        self.assertFalse(f.workspace.exists())

    def test_changed_git_source_even_committed_is_rejected(self):
        f = self.fixture
        (f.repo / 'references/local/els_server/application.py').write_bytes(b'changed business source')
        f.commit()
        with self.assertRaisesRegex(ValueError, 'Git LOCAL source differs'):
            f.initialize()

    def test_git_profile_cannot_omit_one_business_file_and_keep_acceptance_label(self):
        f = self.fixture
        f.formal['channels']['local']['files'].pop()
        (f.repo / 'channels/formal.json').write_bytes(bootstrap.encoded(f.formal))
        f.commit()
        with self.assertRaisesRegex(ValueError, 'complete business index differs'):
            f.initialize()

    def test_dirty_checkout_is_not_executed_or_installed(self):
        f = self.fixture
        (f.repo / 'untracked.py').write_text('raise SystemExit("must never execute")\n')
        with self.assertRaisesRegex(ValueError, 'uncommitted or untracked'):
            f.initialize()
        self.assertFalse(f.workspace.exists())

    def test_unknown_formal_after_existing_install_preserves_runtime(self):
        f = self.fixture
        first = f.initialize()
        pointer = (f.workspace / 'releases/local/current.json').read_bytes()
        selection_path = f.repo / 'channels/current-engine.json'
        selection = bootstrap.read(selection_path)
        selection['accepted']['local']['formal_manifest_sha256'] = 'b' * 64
        selection_path.write_bytes(bootstrap.encoded(selection))
        f.commit()
        with self.assertRaisesRegex(ValueError, 'acceptance differs'):
            f.initialize()
        self.assertEqual(pointer, (f.workspace / 'releases/local/current.json').read_bytes())
        self.assertTrue(Path(first['root']).is_dir())

    def test_corrupted_existing_install_is_never_replaced(self):
        f = self.fixture
        root = Path(f.initialize()['root'])
        app = root / 'els_server/application.py'
        app.write_bytes(b'previous user or unexpected change')
        with self.assertRaisesRegex(ValueError, 'SHA verification'):
            f.initialize()
        self.assertEqual(app.read_bytes(), b'previous user or unexpected change')

    def test_undeclared_business_override_is_rejected(self):
        f = self.fixture
        f.add_runtime('els_server/application.py', b'not accepted business')
        f.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'differs from accepted business'):
            f.initialize()

    def test_saved_database_in_source_package_is_rejected(self):
        f = self.fixture
        f.add_runtime('analysis/client-6c6b5180/integrated-experiment.sqlite3', b'owner database must not ship')
        f.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'player database'):
            f.initialize()

    def test_path_escape_and_case_duplicate_are_rejected(self):
        with self.assertRaises(ValueError):
            bootstrap.rows({'files': [row('../escape', b'x')]})
        with self.assertRaises(ValueError):
            bootstrap.rows({'files': [row('Python/python.exe', b'x'), row('python/python.exe', b'x')]})

    def test_copy_failure_cleans_only_own_stage_and_retry_succeeds(self):
        f = self.fixture
        with patch.object(bootstrap.shutil, 'copyfile', side_effect=OSError('injected disk failure')):
            with self.assertRaisesRegex(OSError, 'injected'):
                f.initialize()
        self.assertFalse((f.workspace / 'releases/local/current.json').exists())
        self.assertEqual([], list((f.workspace / 'releases/local').glob('.first-install-*')))
        self.assertFalse(f.initialize()['reused'])

    def test_source_changes_during_copy_do_not_promote(self):
        f = self.fixture
        original = bootstrap.shutil.copyfile
        changed = False
        def copying(source, destination):
            nonlocal changed
            result = original(source, destination)
            if not changed:
                changed = True
                (f.repo / 'arrived-during-copy.txt').write_text('changed')
            return result
        with patch.object(bootstrap.shutil, 'copyfile', side_effect=copying):
            with self.assertRaisesRegex(ValueError, 'uncommitted or untracked'):
                f.initialize()
        self.assertFalse((f.workspace / 'releases/local/current.json').exists())

    def test_concurrent_os_lock_refuses_then_releases_without_stale_owner(self):
        f = self.fixture
        f.workspace.mkdir(parents=True)
        command = [sys.executable, '-B', '-c',
                   'from pathlib import Path; import sys; sys.path.insert(0,str(Path.cwd())); import local_bootstrap as b; '
                   'c=b.installation_lock(Path(sys.argv[1])); c.__enter__(); '
                   'print("held",flush=True); sys.stdin.readline(); c.__exit__(None,None,None)', str(f.workspace)]
        child = subprocess.Popen(command, cwd=HERE, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, creationflags=bootstrap.FLAGS)
        try:
            self.assertEqual('held', child.stdout.readline().strip())
            with self.assertRaisesRegex(ValueError, 'already running'):
                f.initialize()
        finally:
            child.communicate('\n', timeout=10)
        self.assertFalse(f.initialize()['reused'])

    def test_pointer_atomic_publication_never_replaces_existing(self):
        f = self.fixture
        path = f.root / 'atomic.json'
        bootstrap.atomic_new(path, b'{"first":true}')
        with self.assertRaises(FileExistsError):
            bootstrap.atomic_new(path, b'{"replacement":true}')
        self.assertEqual(path.read_bytes(), b'{"first":true}')
        self.assertEqual([], list(f.root.glob('.atomic.json.*.tmp')))

    def test_pointer_failure_after_promotion_can_recover_complete_tree(self):
        f = self.fixture
        with patch.object(bootstrap, 'atomic_new', side_effect=OSError('pointer I/O interruption')):
            with self.assertRaisesRegex(OSError, 'pointer I/O'):
                f.initialize()
        self.assertFalse((f.workspace / 'releases/local/current.json').exists())
        target = f.workspace / 'releases/local' / f.metadata['release']
        before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()}
        result = f.initialize()
        self.assertTrue(result['recovered'])
        self.assertEqual(before, {str(p.relative_to(target)): p.read_bytes()
                                  for p in target.rglob('*') if p.is_file()})
        self.assertTrue(f.initialize()['reused'])

    def test_incomplete_or_changed_orphan_tree_is_preserved_and_refused(self):
        f = self.fixture
        with patch.object(bootstrap, 'atomic_new', side_effect=OSError('pointer I/O interruption')):
            with self.assertRaises(OSError):
                f.initialize()
        target = f.workspace / 'releases/local' / f.metadata['release']
        config = target / 'config/server.toml'
        config.write_bytes(b'old diagnostic or modified config')
        with self.assertRaisesRegex(ValueError, 'incomplete or changed'):
            f.initialize()
        self.assertEqual(config.read_bytes(), b'old diagnostic or modified config')
        self.assertFalse((f.workspace / 'releases/local/current.json').exists())

    def test_existing_unsigned_self_consistent_rewrite_is_rejected(self):
        f = self.fixture
        root = Path(f.initialize()['root'])
        changed = b'forged business with forged local checksums'
        (root / 'els_server/application.py').write_bytes(changed)
        for name in ('local-business-manifest.json', 'client-bundle-manifest.json'):
            document = bootstrap.read(root / name)
            document['files'] = [row('els_server/application.py', changed) if x['path'] == 'els_server/application.py' else x
                                 for x in document['files']]
            (root / name).write_bytes(bootstrap.encoded(document))
        current = f.workspace / 'releases/local/current.json'
        pointer = bootstrap.read(current)
        pointer['manifest_sha256'] = bootstrap.digest(root / 'local-business-manifest.json')
        current.write_bytes(bootstrap.encoded(pointer))
        with self.assertRaisesRegex(ValueError, 'differs from the signed'):
            f.initialize()
        self.assertEqual((root / 'els_server/application.py').read_bytes(), changed)

    def test_linked_workspace_is_refused_without_external_writes(self):
        f = self.fixture
        external = f.root / 'external'
        external.mkdir()
        cache = f.repo / '.runtime-cache'
        try:
            cache.symlink_to(external, target_is_directory=True)
        except OSError as error:
            self.skipTest('Windows symlink privilege unavailable: ' + str(error))
        try:
            with self.assertRaisesRegex(ValueError, 'Linked'):
                f.initialize()
            self.assertEqual([], list(external.iterdir()))
        finally:
            cache.unlink()

    def test_marker_tampering_and_wrong_save_are_rejected(self):
        f = self.fixture
        root = Path(f.initialize()['root'])
        with self.assertRaisesRegex(ValueError, 'config or save differs'):
            fresh_local_allowed(root, root / 'config/server.toml', f.root / 'other.sqlite3')
        config = root / 'config/server.toml'
        config.write_bytes(config.read_bytes() + b'\n# modified\n')
        with self.assertRaisesRegex(ValueError, 'config changed'):
            fresh_local_allowed(root, config, f.workspace / 'state/integrated.sqlite3')

    def test_no_marker_keeps_legacy_path(self):
        f = self.fixture
        self.assertFalse(fresh_local_allowed(f.runtime, f.runtime / 'config/server.toml', f.root / 'legacy.sqlite3'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
