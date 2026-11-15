"""Local hot reload: lazily imported handlers pick up edited code in place."""
import importlib
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from els_server import hot_reload


class HotReloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        sys.path.insert(0, str(self.root)); self.addCleanup(sys.path.remove, str(self.root))
        self.name = '_hrmod_' + Path(self.tmp.name).name.replace('-', '_')

    def write(self, body):
        (self.root / (self.name + '.py')).write_text(textwrap.dedent(body), encoding='utf8')
        importlib.invalidate_caches()

    def tearDown(self):
        sys.modules.pop(self.name, None)

    def test_lazy_import_sees_reloaded_code(self):
        # The dispatch chain imports handlers inside the call, so a reload is
        # visible on the very next request without touching live sessions.
        self.write('''
            def handle():
                return 'old'
            ''')
        module = importlib.import_module(self.name)
        sys.modules[self.name] = module
        dispatcher = lambda: __import__(self.name, fromlist=['handle']).handle()
        self.assertEqual(dispatcher(), 'old')
        self.write('''
            def handle():
                return 'fixed'
            ''')
        self.assertEqual(hot_reload.reload_modules([self.name]), [self.name])
        self.assertEqual(dispatcher(), 'fixed')

    def test_reload_failure_keeps_previous_module(self):
        self.write('''
            def handle():
                return 'old'
            ''')
        module = importlib.import_module(self.name); sys.modules[self.name] = module
        self.write('''
            def handle(:
                return 'broken'
            ''')
        self.assertEqual(hot_reload.reload_modules([self.name]), [])
        self.assertEqual(module.handle(), 'old')

    def test_stamps_and_first_sighting(self):
        self.write('''
            VALUE = 1
            ''')
        module = importlib.import_module(self.name); sys.modules[self.name] = module
        stamp = hot_reload.stamps([self.name])
        self.assertIn(self.name, stamp)
        self.assertEqual(hot_reload.stamps(['els_server.module_that_is_not_imported']), {})

    def test_enabled_defaults_to_local_profile_only(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ELS_HOT_RELOAD', None)
            self.assertTrue(hot_reload.enabled(type('C', (), {'mode': 'local'})()))
            self.assertFalse(hot_reload.enabled(type('C', (), {'mode': 'friends'})()))
        with patch.dict(os.environ, {'ELS_HOT_RELOAD': '0'}):
            self.assertFalse(hot_reload.enabled(type('C', (), {'mode': 'local'})()))
        with patch.dict(os.environ, {'ELS_HOT_RELOAD': '1'}):
            self.assertTrue(hot_reload.enabled(type('C', (), {'mode': 'friends'})()))

    def test_module_list_reads_state_file(self):
        config = self.root / 'hot-reload.json'
        config.write_text('{"modules": ["els_server.domain.bag_expansion_flow", "not_a_module"]}', encoding='utf8')
        with patch.object(hot_reload, 'CONFIG_FILE', config):
            self.assertEqual(hot_reload.modules(), ('els_server.domain.bag_expansion_flow',))
        config.write_text('{"modules": []}', encoding='utf8')
        with patch.object(hot_reload, 'CONFIG_FILE', config):
            self.assertEqual(hot_reload.modules(), hot_reload.DEFAULT_MODULES)


if __name__ == '__main__':
    unittest.main()
