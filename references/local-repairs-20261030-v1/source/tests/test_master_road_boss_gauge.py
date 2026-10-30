"""Local boss-gauge line overlay (config/local_boss_gauge.json)."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data'
CONFIG = ROOT / 'config/local_boss_gauge.json'
ACTIVE = {'enabled': True, 'maps': {34390: 151}}


class GaugeRuleTests(unittest.TestCase):
    def test_configuration_is_pinned_to_the_observed_map(self):
        from els_server.domain import local_boss_gauge
        rule = local_boss_gauge.rules()
        # Shipped off: the refunded HP cap already yields the 151-line gauge.
        self.assertIs(rule['enabled'], False)
        self.assertEqual(rule['maps'], {34390: 151})
        manifest = json.loads(CONFIG.read_bytes())
        self.assertEqual(manifest['provenance'], 'local_boss_gauge')
        self.assertEqual(manifest['schema_version'], 1)

    def test_overlay_and_pass_through(self):
        from els_server.domain import local_boss_gauge
        with patch.object(local_boss_gauge, 'rules', lambda: ACTIVE):
            self.assertEqual(local_boss_gauge.lines(34390, 1), 151)
            self.assertEqual(local_boss_gauge.lines(34390, 151), 151)
            for dungeon in (34370, 34380, 34400, 34490, 30000, 120000):
                self.assertEqual(local_boss_gauge.lines(dungeon, 1), 1)
                self.assertEqual(local_boss_gauge.lines(dungeon, 70), 70)

    def test_switch_identity_and_bounds(self):
        from els_server.domain import local_boss_gauge
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gauge.json'
            path.write_text(json.dumps({'schema_version': 1, 'provenance': 'local_boss_gauge',
                                        'enabled': False, 'maps': {'34390': 151}}), encoding='utf8')
            with patch.object(local_boss_gauge, 'CONFIG', path):
                local_boss_gauge.rules.cache_clear()
                try:
                    self.assertEqual(local_boss_gauge.lines(34390, 1), 1)
                finally:
                    local_boss_gauge.rules.cache_clear()
            for broken in ({'schema_version': 1, 'provenance': 'other', 'enabled': True, 'maps': {}},
                           {'schema_version': 1, 'provenance': 'local_boss_gauge', 'enabled': 1, 'maps': {}},
                           {'schema_version': 1, 'provenance': 'local_boss_gauge', 'enabled': True,
                            'maps': {'34390': 0}},
                           {'schema_version': 1, 'provenance': 'local_boss_gauge', 'enabled': True,
                            'maps': {'34390': 65536}},
                           {'schema_version': 1, 'provenance': 'local_boss_gauge', 'enabled': True,
                            'maps': {'rosso': 151}}):
                path.write_text(json.dumps(broken), encoding='utf8')
                with self.subTest(broken=broken):
                    with patch.object(local_boss_gauge, 'CONFIG', path):
                        local_boss_gauge.rules.cache_clear()
                        try:
                            with self.assertRaises(ValueError):
                                local_boss_gauge.rules()
                        finally:
                            local_boss_gauge.rules.cache_clear()
        self.assertIs(local_boss_gauge.rules()['enabled'], False)

    def test_missing_configuration_keeps_the_imported_lines(self):
        from els_server.domain import local_boss_gauge
        with patch.object(local_boss_gauge, 'CONFIG', Path(tempfile.gettempdir()) / 'no-such-gauge.json'):
            local_boss_gauge.rules.cache_clear()
            try:
                self.assertEqual(local_boss_gauge.lines(34390, 1), 1)
            finally:
                local_boss_gauge.rules.cache_clear()


RUN_ID = str(uuid.UUID('00000000-0000-4000-8000-000000000001'))
DISABLED = {'enabled': False, 'maps': {}}


@unittest.skipUnless((DATA / 'client/catalog.sqlite3').is_file(), 'version-locked runtime catalog required')
class RuntimeGaugeTests(unittest.TestCase):
    @staticmethod
    def boss(dungeon, rule):
        from els_server.domain import local_boss_gauge
        from els_server.domain.dungeon_routes import DungeonRun
        with patch.object(local_boss_gauge, 'rules', lambda: rule):
            run = DungeonRun(dungeon, RUN_ID)
        return next(n for n in run.current['npcs'] if n.get('boss'))

    def test_rosso_wire_carries_the_observed_line_count(self):
        # The entry keeps the imported declaration; only the encoded resource
        # (0x58 -> DTO 0x77, the field 1693620 divides the maximum by) changes.
        imported = self.boss(34390, DISABLED)
        observed = self.boss(34390, ACTIVE)
        self.assertEqual(imported['boss_lines'], 1)
        self.assertEqual(observed['boss_lines'], 1)
        self.assertEqual(imported['key'], observed['key'])
        self.assertEqual(len(imported['wire']), len(observed['wire']))
        changed = [i for i, (a, b) in enumerate(zip(imported['wire'], observed['wire'])) if a != b]
        # 1 = 0x00 0x01 and 151 = 0x00 0x97 share the high byte.
        self.assertEqual(len(changed), 1)

    def test_other_maps_keep_the_imported_line_count(self):
        for dungeon in (34370, 34380, 34400, 34490):
            with self.subTest(dungeon=dungeon):
                imported = self.boss(dungeon, DISABLED)
                observed = self.boss(dungeon, ACTIVE)
                self.assertEqual(imported['boss_lines'], 1)
                self.assertEqual(imported['wire'], observed['wire'])


if __name__ == '__main__':
    unittest.main()
