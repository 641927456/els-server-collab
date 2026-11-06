"""Native per-line identification: 992 equipment profiles and 188 line pools.

The identification catalog now carries the native option shape of each equipment
template (one to four independent option lines) instead of one shared 45-outcome
group. These tests pin the parts a player can observe: the number of generated
lines, the pools they come from, the refusal to guess an unresolved pool, and the
"unidentified until identified" state of a fresh native item.
"""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data'


def first_roll(size):
    return 0


def last_roll(size):
    return size - 1


class NativeIdentificationCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from els_server.domain import identification_ui as ui
        cls.ui = ui
        cls.catalog = ui.catalog()

    def templates_by_arity(self):
        buckets = {}
        for key, row in self.catalog['native_templates'].items():
            buckets.setdefault(len(row['native_groups']), []).append(int(key))
        return {arity: sorted(values) for arity, values in sorted(buckets.items())}

    def test_the_payload_matches_the_constant_the_reader_checks(self):
        raw = (DATA / 'identification_ui.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '975267cf7efc8bbda24ad26d6202ff9f590bef64e140ed0c9a2892a5d8d03df9')

    def test_every_native_template_maps_one_pool_to_each_native_line(self):
        pools = self.catalog['native_pools']
        self.assertGreaterEqual(len(self.catalog['native_templates']), 900)
        for key, row in self.catalog['native_templates'].items():
            with self.subTest(template=key):
                self.assertTrue(1 <= len(row['native_groups']) <= 4)
                self.assertEqual(len(row['pool_groups']), len(row['native_groups']))
                for group in row['pool_groups']:
                    self.assertIn(str(group), pools)

    def test_every_native_pool_is_a_complete_hundred_percent_distribution(self):
        for key, pool in self.catalog['native_pools'].items():
            with self.subTest(pool=key):
                self.assertEqual(sum(row['weight'] for row in pool['outcomes']), 10000)
                options = {str(row['option']) for row in pool['outcomes']}
                self.assertEqual(options, set(pool['options']))

    def test_generated_line_count_follows_the_native_equipment_shape(self):
        for arity, templates in self.templates_by_arity().items():
            template = templates[0]
            row = self.catalog['native_templates'][str(template)]
            for roll in (first_roll, last_roll):
                with self.subTest(template=template, arity=arity):
                    values = self.ui.draw_initial(template, roll)
                    self.assertEqual(len(values), arity)
                    for value, group in zip(values, row['pool_groups']):
                        self.assertIn(str(value), self.catalog['native_pools'][str(group)]['options'])

    def test_a_generated_vector_validates_against_its_own_template(self):
        for arity, templates in self.templates_by_arity().items():
            template = templates[-1]
            with self.subTest(template=template, arity=arity):
                values = self.ui.draw_initial(template, first_roll)
                self.assertEqual(self.ui.validate(template, values), values)

    def test_unresolved_native_pools_are_never_guessed(self):
        unresolved = sorted(self.catalog['unresolved_native_templates'], key=int)
        self.assertEqual(unresolved, ['118332', '118333', '118334', '118335'])
        for key in unresolved:
            template = int(key)
            with self.subTest(template=template):
                for attempt in (lambda: self.ui.draw_initial(template, first_roll),
                                lambda: self.ui.require_template(template, reset=True)):
                    with self.assertRaises(ValueError):
                        attempt()

    def test_a_fresh_native_equipment_item_is_pending_until_identified(self):
        template = self.templates_by_arity()[2][0]
        item = {'template': template, 'group': 1, 'count': 1}
        self.assertTrue(self.ui.initial_pending(item))
        item['identified'] = True
        self.assertFalse(self.ui.initial_pending(item))

    def test_require_initial_complete_rejects_an_unidentified_item(self):
        template = self.templates_by_arity()[2][0]
        with self.assertRaises(ValueError):
            self.ui.require_initial_complete({'template': template, 'group': 1, 'count': 1, 'identified': False})
        with self.assertRaises(ValueError):
            self.ui.require_initial_complete({'template': template, 'group': 1, 'count': 1})
        full = self.ui.draw_initial(template, first_roll)
        self.ui.require_initial_complete({'template': template, 'group': 1, 'count': 1,
                                          'option_groups': {'1': full}})

    def test_compatibility_rows_still_read_their_historical_vector(self):
        rows = self.catalog['compatibility_slots']['rows']
        self.assertEqual(len(rows), 64)
        checked = 0
        for key, row in rows.items():
            if 'pool' not in row:
                continue
            checked += 1
            template = int(key)
            with self.subTest(template=template):
                pool = self.ui.template_pool(template)
                self.assertIsNotNone(pool)
                self.assertEqual(row['native_groups'], [pool['native_group']] * len(row['native_groups']))
                option = pool['outcomes'][0]['option']
                self.assertEqual(self.ui.validate(template, [option]), [option])
        self.assertGreater(checked, 0)


class AccessoryGroupIdentificationTests(unittest.TestCase):
    def test_the_original_accessory_draws_both_of_its_lines(self):
        from els_server.domain import accessory_identification as accessory
        self.assertEqual(accessory.catalog()['line_count'], 2)
        values = accessory.draw(first_roll)
        self.assertEqual(len(values), 2)
        self.assertEqual(accessory.validate(30603, values), values)

    def test_a_grouped_accessory_draws_the_lines_its_profile_declares(self):
        from els_server.domain import accessory_identification as accessory
        profiles = accessory.groups_catalog()['templates']
        self.assertGreater(len(profiles), 80)
        for key in sorted(profiles)[:12]:
            template = int(key)
            row = profiles[key]
            with self.subTest(template=template):
                values = accessory.draw(first_roll, template)
                self.assertEqual(len(values), len(row['native_groups']))
                self.assertEqual(accessory.validate(template, values), values)


class GuideReactorIdentificationTests(unittest.TestCase):
    def test_the_four_guide_reactors_accept_only_their_fixed_native_vector(self):
        from els_server.domain.growth_guide_boxes import boxes
        for row in boxes()[722236]['outputs']:
            template = row['template']
            expected = row['option_groups']['1']
            with self.subTest(template=template):
                from els_server.domain.identification_ui import validate
                self.assertEqual(validate(template, expected), expected)
                with self.assertRaises(ValueError):
                    validate(template, [])


if __name__ == '__main__':
    unittest.main()
