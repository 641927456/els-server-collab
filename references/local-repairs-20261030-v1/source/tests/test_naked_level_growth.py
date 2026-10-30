"""Naked base inputs follow the verified native relative level law."""
import json,struct,unittest
from pathlib import Path
from els_server.domain.character_stats import (combat_attributes,combat_values,flat_indices,
                                              level_multipliers,_base,_parameters)

ROOT=Path(__file__).resolve().parents[1]
CHARACTER=dict(unit_class=100,unit_type=1)


class NakedLevelGrowthTests(unittest.TestCase):
    def test_config_declares_a_local_curve_not_a_retail_measurement(self):
        policy=json.loads((ROOT/'config/combat_rules.json').read_text(encoding='utf8'))
        self.assertEqual(policy['provenance'],'local_policy')
        self.assertIs(policy['retail_base_verified'],False)
        self.assertIs(policy['level_growth_verified'],False)
        self.assertEqual(policy['level_growth']['provenance'],'native_equipment_curve_relative')
        self.assertEqual(policy['level_growth']['reference_level'],1)

    def test_level_one_reproduces_the_configured_placeholder(self):
        base=tuple(float(v) for v in _base()[0])
        self.assertEqual(level_multipliers(1),(1.0,1.0))
        self.assertEqual(combat_values(dict(CHARACTER,level=1)),base)
        # No character context keeps the historical unscaled tuple.
        self.assertEqual(combat_values(),base)
        self.assertEqual(struct.unpack('>7f',combat_attributes()),base)

    def test_multipliers_match_the_pinned_native_knum_constants(self):
        physical,hp=_parameters()
        one,growth,subtract,subtract_growth,_half=physical
        pivot=one-subtract;rate=growth-subtract_growth
        for level in (2,40,80,99):
            health,attribute=level_multipliers(level)
            n=level-1
            self.assertAlmostEqual(health,1+n*hp[1],places=5)
            self.assertAlmostEqual(attribute,(pivot+n*rate)/pivot,places=5)

    def test_growth_is_monotonic_and_keeps_the_wire_layout(self):
        for level in (1,10,40,70,99):
            values=combat_values(dict(CHARACTER,level=level))
            self.assertEqual(len(values),7)
            payload=combat_attributes(dict(CHARACTER,level=level))
            self.assertEqual(len(payload),28)
            self.assertEqual(struct.unpack('>7f',payload),values)
        low=combat_values(dict(CHARACTER,level=1));high=combat_values(dict(CHARACTER,level=99))
        self.assertTrue(all(a<=b for a,b in zip(low,high)))
        self.assertGreater(high[1],low[1]*50)  # attack is not a token constant any more
        self.assertGreater(high[0],low[0]*10)

    def test_disabling_the_block_restores_a_flat_base(self):
        from unittest.mock import patch
        with patch('els_server.domain.character_stats._growth',return_value=None):
            self.assertIsNone(level_multipliers(99))
            self.assertEqual(combat_values(dict(CHARACTER,level=99)),tuple(float(v) for v in _base()[0]))

    def test_flat_indices_hold_a_field_at_its_reference_value(self):
        from unittest.mock import patch
        from els_server.domain import character_stats as module
        base=tuple(float(v) for v in _base()[0])
        module._growth.cache_clear()
        real=module._growth()
        self.assertEqual(sorted(flat_indices()),sorted(real[3]))
        try:
            with patch.object(module,'_growth',return_value=(real[0],real[1],real[2],frozenset({0,5}))):
                values=module.combat_values(dict(CHARACTER,level=99))
                self.assertEqual(values[0],base[0])
                self.assertEqual(values[5],base[5])
                self.assertGreater(values[1],base[1])
        finally:
            module._growth.cache_clear()

    def test_rejects_unusable_levels_and_drifted_constants(self):
        for bad in (0,-1,256,True,1.5,'9'):
            with self.assertRaises(ValueError):level_multipliers(bad)
        # A pivot of zero means the native table no longer cancels; refuse to
        # invent a curve instead of silently dividing by it.
        from unittest.mock import patch
        from els_server.domain import character_stats as module
        module._growth.cache_clear()
        try:
            with patch.object(module,'_parameters',return_value=((1,.15,1,.0225,.5),(1,.17,10,1.1,.5))):
                with self.assertRaises(ValueError):module._growth()
        finally:
            module._growth.cache_clear()


if __name__=='__main__':unittest.main()
