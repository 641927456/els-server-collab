"""Native life-content catalog: expedition, resonance potions, fishing, pet gear.

Evidence: analysis/pet-support-20261015/LifeContentData.lua.tables.json — 9
expedition regions, 36 missions, 36 risk factors, 52 El-resonance experience
potions, 4 life-spirit restore potions, 16 fishing premium items and a 19-item pet
accessory whitelist, plus the two global action costs.

The assertions pin the costs and rewards exactly, so a later integration never has
to re-derive them. Two omissions are deliberate and are asserted here: the two
unnamed trailing arguments of AddElResonanceExpPotion stay verbatim under
`extra`, and the expedition display textures are dropped as render resources.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from els_server.domain import life_content
from els_server.game_data import CLIENT_SHA

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data/life_content.json'


class LifeContentPayload(unittest.TestCase):
    def setUp(self):
        life_content._payload.cache_clear()
        self.payload = json.loads(DATA.read_text(encoding='utf8'))

    def test_payload_pins_the_current_client(self):
        self.assertEqual(self.payload['client_sha256'], CLIENT_SHA)
        self.assertEqual(self.payload['schema_version'], 1)

    def test_every_count_is_exact(self):
        summary = life_content.summary()
        self.assertEqual(summary['regions'], 9)
        self.assertEqual(summary['missions'], 36)
        self.assertEqual(summary['risk_factors'], 36)
        self.assertEqual(summary['resonance_exp_potions'], 52)
        self.assertEqual(summary['life_spirit_restore_potions'], 4)
        self.assertEqual(summary['fishing_premium_items'], 16)
        self.assertEqual(summary['pet_accessory_items'], 19)
        self.assertEqual(summary['difficulty_range'], [100, 1000])

    def test_every_region_has_exactly_four_missions(self):
        regions = life_content.regions()
        self.assertEqual(len(regions), 9)
        for region_id in regions:
            self.assertEqual(len(life_content.missions_for_region(region_id)), 4, region_id)
        self.assertEqual(life_content.missions_for_region(99), ())

    def test_every_mission_points_at_a_real_region_and_risk_factor(self):
        regions = life_content.regions()
        risk = life_content.risk_factors()
        for mission_id, body in life_content.missions().items():
            self.assertIn(body['region_id'], regions, mission_id)
            self.assertIn(body['risk_factor_id'], risk, mission_id)
            self.assertTrue(body['reward_items'], mission_id)
            self.assertGreater(body['difficulty_point'], 0, mission_id)
            self.assertGreater(body['consumed_ed'], 0, mission_id)
            self.assertGreater(body['exploration_minutes'], 0, mission_id)

    def test_the_risk_factors_are_three_attributes_of_twelve(self):
        attributes = {}
        for body in life_content.risk_factors().values():
            attributes[body['pet_attribute']] = attributes.get(body['pet_attribute'], 0) + 1
        self.assertEqual(attributes, {1: 12, 2: 12, 3: 12})

    def test_resonance_potions_keep_the_unnamed_arguments_verbatim(self):
        potions = self.payload['resonance_exp_potions']
        self.assertEqual(len(potions), 52)
        self.assertEqual(life_content.resonance_potion(135938), {'exp': 1000000, 'extra': [0, 1]})
        for item_id, body in potions.items():
            self.assertGreater(body['exp'], 0, item_id)
            self.assertEqual(len(body['extra']), 2, item_id)
        self.assertIn('does not name them', ' '.join(self.payload['not_claimed']))

    def test_restore_potions_all_last_one_day(self):
        potions = self.payload['life_spirit_restore_potions']
        self.assertEqual(len(potions), 4)
        self.assertEqual({body['minutes'] for body in potions.values()}, {1440})
        self.assertEqual(life_content.restore_potion(135952), {'minutes': 1440})

    def test_the_pet_accessory_whitelist_is_unique(self):
        accessories = life_content.pet_accessories()
        self.assertEqual(len(accessories), 19)
        self.assertEqual(len(set(accessories)), 19)
        self.assertTrue(life_content.is_pet_accessory(135972))
        self.assertFalse(life_content.is_pet_accessory(1))

    def test_the_global_action_costs_are_recorded(self):
        self.assertEqual(life_content.policy_values(),
                         {'life_spirit_per_action': 20, 'endurance_per_action': 40})

    def test_no_render_field_leaked_into_the_catalog(self):
        forbidden = {'m_strImageTextureFile', 'm_strImageTextureKey', 'texture', 'gfx'}
        stack = [self.payload['expedition']]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                self.assertFalse(forbidden & set(node), node.keys())
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)

    def test_unknown_ids_return_none(self):
        self.assertIsNone(life_content.region(99))
        self.assertIsNone(life_content.risk_factor(99))
        self.assertIsNone(life_content.mission(99))
        self.assertIsNone(life_content.resonance_potion(1))
        self.assertIsNone(life_content.restore_potion(1))
        self.assertIsNone(life_content.fishing_premium(1))


if __name__ == '__main__':
    unittest.main()
