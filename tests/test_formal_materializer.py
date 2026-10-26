"""Pinning must fail closed before a runtime can replace anything."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.materialize_formal_runtime import materialize, plan


class MaterializerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        (self.repo / 'runtime-assets.lock.json').write_text('{"files": []}', encoding='utf8')
        (self.repo / 'source.py').write_bytes(b'value = 1\n')
        self.entry = dict(path='els_server/source.py', source='source.py', size=10,
                          sha256=hashlib.sha256(b'value = 1\n').hexdigest())
        self.manifest = {'channels': {'local': {'release': 'fixture', 'files': [self.entry]}}}

    def test_exact_rebuild_and_no_overwrite(self):
        out = self.root / 'output'
        materialize(self.repo, self.manifest, 'local', out)
        self.assertEqual((out / self.entry['path']).read_bytes(), b'value = 1\n')
        with self.assertRaises(ValueError):
            materialize(self.repo, self.manifest, 'local', out)
        self.assertTrue((out / 'engine-source-receipt.json').is_file())

    def test_changed_source_leaves_no_runtime(self):
        (self.repo / 'source.py').write_bytes(b'value = 2\n')
        with self.assertRaises(ValueError):
            materialize(self.repo, self.manifest, 'local', self.root / 'output')
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['repo'])

    def test_traversal_and_windows_aliases(self):
        for path in ('../escaped.py', '/absolute.py', 'a/../b.py', 'a//b.py', 'C:/evil.py',
                     'a\\evil.py', 'a/nul.py', 'a/COM1', 'a/file. ', './a.py'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                candidate = deepcopy(self.manifest)
                candidate['channels']['local']['files'][0]['path'] = path
                plan(self.repo, candidate, 'local')

    def test_case_collision_rejected(self):
        self.manifest['channels']['local']['files'].append(dict(self.entry, path='ELS_SERVER/source.py'))
        with self.assertRaises(ValueError):
            plan(self.repo, self.manifest, 'local')

    def test_assets_require_existing_lock_and_exact_bytes(self):
        candidate = deepcopy(self.manifest)
        entry = candidate['channels']['local']['files'][0]
        entry['asset'] = entry.pop('source')
        with self.assertRaises(ValueError):
            plan(self.repo, candidate, 'local')
        entry['asset'] = entry['path']
        (self.repo / 'runtime-assets.lock.json').write_text(json.dumps({'files': [entry]}), encoding='utf8')
        self.assertIsNone(plan(self.repo, candidate, 'local')[0][1])
        assets = self.root / 'assets'
        (assets / 'els_server').mkdir(parents=True)
        (assets / entry['path']).write_bytes(b'value = 2\n')
        with self.assertRaises(ValueError):
            plan(self.repo, candidate, 'local', assets)


if __name__ == '__main__':
    unittest.main()
