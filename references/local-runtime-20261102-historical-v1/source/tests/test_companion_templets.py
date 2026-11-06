"""Native pet and mount behaviour templets decoded from the client resources.

Evidence: analysis/shop-standalone-20261015/resources/PetTemplet.tables.json (331
AddPetTemplet records) and RidingPetTemplet.tables.json (139 AddRidingPetTemplet
records), with the PET_UNIT_ID / RIDING_PET_UNIT_ID / PET_ATTRIBUTE symbols
resolved through analysis/client-6c6b5180/resource-scripts/Enum.tables.json.

The activation catalog at analysis/pet-mount-20261015/activation-catalog.json was
built from PetData / RidingPetData only, so it knows the item -> unit mapping but
not a single growth or skill field. These assertions pin the decoded layer and the
coverage of that mapping, and they must not be read as an activation test.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from els_server.domain import companion_templets
from els_server.game_data import CLIENT_SHA

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'analysis/pet-mount-20261015/activation-catalog.json'
DATA = ROOT / 'els_server/data/companion_templets.json'


class TempletPayload(unittest.TestCase):
    def setUp(self):
        companion_templets._payload.cache_clear()
        self.payload = json.loads(DATA.read_text(encoding='utf8'))

    def test_payload_pins_the_current_client(self):
        self.assertEqual(self.payload['client_sha256'], CLIENT_SHA)
        self.assertEqual(self.payload['schema_version'], 1)
        self.assertEqual(self.payload['policy'], 'companion-templet-catalog-only-v1')

    def test_every_pet_symbol_resolves_to_a_numeric_unit(self):
        pets = companion_templets.catalog('pet')
        self.assertEqual(len(pets), 331)
        self.assertTrue(all(isinstance(k, int) and k > 0 for k in pets))
        self.assertTrue(all(v['symbol'] and not v['symbol'].startswith('PET_UNIT_ID')
                            for v in pets.values()))
        symbols = [v['symbol'] for v in pets.values()]
        self.assertEqual(len(symbols), len(set(symbols)))

    def test_every_mount_symbol_resolves_to_a_numeric_unit(self):
        mounts = companion_templets.catalog('mount')
        self.assertEqual(len(mounts), 139)
        self.assertTrue(all(isinstance(k, int) and k > 0 for k in mounts))
        symbols = [v['symbol'] for v in mounts.values()]
        self.assertEqual(len(symbols), len(set(symbols)))

    def test_attribute_is_an_enum_value_not_a_string(self):
        pets = companion_templets.catalog('pet')
        seen = {v['attribute_symbol'] for v in pets.values() if v['attribute_symbol']}
        self.assertEqual(seen, {'WILD', 'SPIRIT', 'INTELLIGENCE'})
        for v in pets.values():
            if v['attribute_symbol'] is None:
                self.assertIsNone(v['attribute'])
            else:
                self.assertIn(v['attribute'], (0, 1, 2, 3))
                self.assertNotEqual(v['attribute'], 0)  # PET_ATTRIBUTE.NONE never appears


class PetGrowth(unittest.TestCase):
    def setUp(self):
        companion_templets._payload.cache_clear()

    def test_ancient_pporu_growth_tiers(self):
        entry = companion_templets.templet('pet', 3)
        self.assertEqual(entry['symbol'], 'PUI_PETTE_ANCIENT_PPORU')
        self.assertEqual(entry['attribute_symbol'], 'WILD')
        self.assertEqual(entry['evolution_exp'], [38160, 152640, 305280, 534240])
        self.assertEqual(entry['evolution_scripts'][0], 'BasicPet.lua')
        self.assertEqual(len(entry['evolution_scripts']), 4)

    def test_appetite_and_caprice_are_floats(self):
        entry = companion_templets.templet('pet', 3)
        self.assertIsInstance(entry['appetite'], float)
        self.assertIsInstance(entry['caprice'], float)

    def test_unknown_unit_returns_none(self):
        self.assertIsNone(companion_templets.templet('pet', 99999999))
        self.assertEqual(companion_templets.evolution_exp(99999999), [])
        self.assertEqual(companion_templets.skill_symbols('pet', 99999999), {})

    def test_skill_symbols_are_grouped_per_kind(self):
        skills = companion_templets.skill_symbols('pet', 3)
        self.assertEqual(skills['attack'], ['SKILL_ANCIENT_01', 'SKILL_ANCIENT_02', 'SKILL_ANCIENT_03'])
        self.assertEqual(set(skills['cheer']), {'SKILL_CHEER'})
        self.assertTrue(all(v for v in skills.values()))  # no null tiers


class MountRules(unittest.TestCase):
    def setUp(self):
        companion_templets._payload.cache_clear()

    def test_nasod_mobi_rates_and_size(self):
        entry = companion_templets.templet('mount', 1)
        self.assertEqual(entry['symbol'], 'RPUI_NASOD_MOBI')
        self.assertEqual(entry['script'], 'RidingPet_Nasod_Mobi.lua')
        self.assertEqual(entry['stamina_recovery_rate'], 1)
        self.assertEqual(entry['stamina_increase_rate'], 1)
        self.assertEqual(entry['viewer_size'], [0.6, 0.6, 0.6])
        self.assertEqual(entry['name_str_id'], 'STR_ID_29469')

    def test_mount_globals_are_not_claimed_as_decoded(self):
        rules = companion_templets.mount_rules()
        self.assertTrue(rules)
        for name, value in rules.items():
            self.assertIn('closure_index', value)
            self.assertIs(value['decoded'], False,
                          'the stamina and speed formulas are not decoded: %s' % name)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            companion_templets.catalog('dragon')


@unittest.skipUnless(CATALOG.is_file(), 'runtime asset archive not present')
class ActivationCoverage(unittest.TestCase):
    """The activation mapping is a separate artifact; assert the two agree."""

    def setUp(self):
        companion_templets._payload.cache_clear()
        self.activation = json.loads(CATALOG.read_text(encoding='utf8'))

    def test_every_activated_mount_has_a_templet(self):
        units = {u for v in self.activation['mount'].values() for u, _ in v['outcomes']
                 if isinstance(u, int)}
        missing = units - set(companion_templets.catalog('mount'))
        self.assertEqual(missing, set())

    def test_activated_pets_without_a_templet_are_region_aliases(self):
        units = {u for v in self.activation['pet'].values() for u, _ in v['outcomes']
                 if isinstance(u, int)}
        missing = units - set(companion_templets.catalog('pet'))
        enum = json.loads((ROOT / 'analysis/client-6c6b5180/resource-scripts/Enum.tables.json')
                          .read_text(encoding='utf8'))['PET_UNIT_ID']
        reverse = {v: k for k, v in enum.items()}
        # 19 entries remain: event and _USA_TRANS_F aliases whose base pet owns the templet.
        for unit in missing:
            name = reverse.get(unit, '')
            self.assertTrue(name.endswith(('_EVENT', '_EVENT_F')) or '_USA_TRANS_F' in name,
                            'activated pet %s (%s) has no templet and is not an alias' % (unit, name))


if __name__ == '__main__':
    unittest.main()
