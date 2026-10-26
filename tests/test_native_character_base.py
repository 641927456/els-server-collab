"""Public documented examples and source guards without a private runtime pack."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from els_server.domain import native_character_base as base


class DocumentedCharacterBaseTests(unittest.TestCase):
    def setUp(self):
        base.rules.cache_clear()
        self.addCleanup(base.rules.cache_clear)
        self.reference={n:(10000.,400.,400.,0.,0.,100.,100.) for n in range(1,16)}
        self.tables=patch('els_server.domain.character_stats._tables',return_value={'CHARACTER_RELATIVE_STAT_TABLE':self.reference})
        self.tables.start();self.addCleanup(self.tables.stop)
        self.client=patch.object(base,'client_data',return_value=SimpleNamespace(unit=lambda cls:{'unitType':1}))
        self.client.start();self.addCleanup(self.client.stop)

    def test_published_examples_exclude_equipment_and_job_bonus(self):
        cases={1:(10000.,320.,320.,0.,0.,80.,80.),50:(83500.,761.,761.,0.,0.,190.25,190.25),99:(157000.,1202.,1202.,0.,0.,300.5,300.5)}
        for level,want in cases.items():
            with self.subTest(level=level):
                self.assertEqual(base.values(dict(unit_class=1,unit_type=1,level=level)),want)
                self.assertEqual(base.values(dict(unit_class=100,unit_type=1,level=level)),want)

    def test_reject_wrong_role_and_unplayable_levels(self):
        for level in (0,100,True,1.0):
            with self.assertRaisesRegex(ValueError,'Base level bound'):
                base.values(dict(unit_class=1,unit_type=1,level=level))
        for character in (dict(unit_class=1,unit_type=5,level=99),dict(unit_class=True,level=99),dict(unit_class=1,unit_type=True,level=99)):
            with self.assertRaisesRegex(ValueError,'Base role identity'):base.values(character)

    def test_refuse_changed_native_initial_reference(self):
        self.reference[15]=(10000.,410.,400.,0.,0.,100.,100.)
        with self.assertRaisesRegex(ValueError,'Base initial-client reference changed'):base.rules()

    def test_provenance_does_not_claim_original_growth_function(self):
        policy=base.rules()
        self.assertTrue(policy['public_growth_rule_authorized'])
        self.assertFalse(policy['retail_base_verified'])
        self.assertFalse(policy['native_client_growth_function_verified'])
        self.assertEqual(base.values(),(10000.,320.,320.,0.,0.,80.,80.))


if __name__=='__main__':unittest.main()
