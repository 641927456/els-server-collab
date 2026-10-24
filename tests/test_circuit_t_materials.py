import unittest


class CircuitTierMaterialTests(unittest.TestCase):
    def test_t_circuit_uses_policy_option_pool(self):
        from els_server.domain import equipment_circuit_rules as circuits
        row = circuits.material(118590)
        self.assertIsNotNone(row)
        self.assertEqual((row['part'], row['shape'], row['color']), (8, 3, 1))
        self.assertEqual(len(row['options']), 253)
        self.assertEqual(circuits.material(118594)['color'], 2)
        self.assertEqual(circuits.material(118598)['color'], 3)
        self.assertEqual(circuits.material(118614)['shape'], 5)

    def test_popular_family_uses_policy_option_pool(self):
        from els_server.domain import equipment_circuit_rules as circuits
        row = circuits.material(118446)
        self.assertIsNotNone(row)
        self.assertEqual((row['part'], row['shape'], row['color']), (8, 1, 1))
        self.assertEqual(len(row['options']), 253)

    def test_t_circuit_gm_options_are_selectable(self):
        from els_server.domain import gm_item_options
        listing = gm_item_options.spec(118590)
        self.assertEqual(listing['kind'], 'choice')
        self.assertGreater(len(listing['choices']), 0)
        special = listing['choices'][0]
        self.assertEqual(special['id'], 100900000)
        self.assertIn('链接电路属性合计', special['label'])
        self.assertEqual(gm_item_options.apply(118590, {'1': [special['id']]}), {'1': [special['id']]})


if __name__ == '__main__':
    unittest.main()
