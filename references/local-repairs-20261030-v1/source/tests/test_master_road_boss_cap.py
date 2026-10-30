"""Master Road imported boss HP cap (config/local_boss_hp_cap.json)."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data'
CAP = ROOT / 'config/local_boss_hp_cap.json'

MASTER_ROAD = (34370, 34380, 34390, 34400, 34410, 34420, 34430, 34440,
               34450, 34460, 34470, 34480, 34490, 34500, 34690, 34700)
# default:boss profile at level 99: 113340 + 17005.6 x 99, encoded as float32.
TARGET = 1796894.375
IMPORTED_BOSSES = {
    34370: 505514880.0, 34380: 2138716800.0, 34390: 1866516480.0,
    34400: 6999436800.0, 34410: 972144000.0, 34420: 3888576000.0,
    34430: 1477658880.0, 34440: 3888576000.0, 34450: 1866516480.0,
    34460: 6999436800.0, 34470: 1866516480.0, 34480: 6999436800.0,
    34490: TARGET, 34500: 13998873600.0, 34690: 1866516480.0,
    34700: 6999436800.0,
}
ORDINARY = {30000.0, 119702.0, 432064.0}
ACTIVE = {'enabled': True, 'maps': {dungeon: 1.0 for dungeon in MASTER_ROAD}}


class CapRuleTests(unittest.TestCase):
    def test_configuration_is_pinned_to_the_master_road_family(self):
        from els_server.domain import local_boss_cap
        rule = local_boss_cap.rules()
        self.assertIs(rule['enabled'], True)
        self.assertEqual(set(rule['maps']), set(MASTER_ROAD))
        self.assertTrue(all(multiplier == 1.0 for multiplier in rule['maps'].values()))
        manifest = json.loads(CAP.read_bytes())
        self.assertEqual(manifest['provenance'], 'local_boss_hp_cap')
        self.assertEqual(manifest['schema_version'], 1)

    def test_target_is_the_lv99_boss_profile_value(self):
        from els_server.domain import local_boss_cap
        for dungeon in MASTER_ROAD:
            with self.subTest(dungeon=dungeon):
                self.assertEqual(local_boss_cap.target(dungeon), TARGET)

    def test_imported_boss_values_are_capped_and_idempotent(self):
        from els_server.domain import local_boss_cap
        from els_server.domain.local_boss_cap import apply
        for dungeon, imported in IMPORTED_BOSSES.items():
            with self.subTest(dungeon=dungeon):
                with patch.object(local_boss_cap, 'rules', lambda: ACTIVE):
                    self.assertEqual(apply(dungeon, imported), TARGET)
                    self.assertEqual(apply(dungeon, apply(dungeon, imported)), TARGET)

    def test_playable_and_unlisted_values_pass_through(self):
        from els_server.domain import local_boss_cap
        from els_server.domain.local_boss_cap import apply
        with patch.object(local_boss_cap, 'rules', lambda: ACTIVE):
            for dungeon in MASTER_ROAD:
                for value in ORDINARY:
                    self.assertEqual(apply(dungeon, value), value)
            for dungeon in (0, 34000, 34340, 34350, 34360, 120000):
                self.assertEqual(apply(dungeon, 199692877037568.0), 199692877037568.0)

    def test_switch_and_identity_validation(self):
        from els_server.domain import local_boss_cap
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cap.json'
            path.write_text(json.dumps({'schema_version': 1, 'provenance': 'local_boss_hp_cap',
                                        'enabled': False, 'maps': {'34370': 1.0}}), encoding='utf8')
            with patch.object(local_boss_cap, 'CONFIG', path):
                local_boss_cap.rules.cache_clear()
                try:
                    self.assertEqual(local_boss_cap.apply(34370, 505514880.0), 505514880.0)
                finally:
                    local_boss_cap.rules.cache_clear()
            path.write_text(json.dumps({'schema_version': 1, 'provenance': 'other',
                                        'enabled': True, 'maps': {}}), encoding='utf8')
            with patch.object(local_boss_cap, 'CONFIG', path):
                local_boss_cap.rules.cache_clear()
                try:
                    with self.assertRaises(ValueError):
                        local_boss_cap.rules()
                finally:
                    local_boss_cap.rules.cache_clear()
        self.assertIs(local_boss_cap.rules()['enabled'], True)

    def test_missing_configuration_disables_the_cap(self):
        from els_server.domain import local_boss_cap
        with patch.object(local_boss_cap, 'CONFIG', Path(tempfile.gettempdir()) / 'no-such-cap.json'):
            local_boss_cap.rules.cache_clear()
            try:
                self.assertEqual(local_boss_cap.apply(34370, 505514880.0), 505514880.0)
            finally:
                local_boss_cap.rules.cache_clear()


@unittest.skipUnless((DATA / 'client/catalog.sqlite3').is_file(), 'version-locked runtime catalog required')
class RuntimeRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from els_server.domain.dungeon_routes import DungeonRun
        cls.runs = {dungeon: DungeonRun(dungeon, uuid.uuid4().hex) for dungeon in MASTER_ROAD}

    def test_every_boss_is_killable_and_nothing_exceeds_the_target(self):
        for dungeon, run in self.runs.items():
            with self.subTest(dungeon=dungeon):
                npcs = run.current['npcs']
                bosses = [n for n in npcs if n.get('boss')]
                self.assertEqual(len(bosses), 1)
                self.assertEqual(bosses[0]['hp'], TARGET)
                others = [n['hp'] for n in npcs if not n.get('boss')]
                self.assertTrue(all(0 < hp <= TARGET for hp in others))

    def test_disabling_the_cap_restores_the_imported_boss(self):
        from els_server.domain import local_boss_cap
        from els_server.domain.dungeon_routes import DungeonRun
        with patch.object(local_boss_cap, 'rules', lambda: {'enabled': False, 'maps': {}}):
            run = DungeonRun(34370, uuid.uuid4().hex)
        boss = next(n for n in run.current['npcs'] if n.get('boss'))
        self.assertEqual(boss['hp'], IMPORTED_BOSSES[34370])


if __name__ == '__main__':
    unittest.main()
