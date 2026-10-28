"""Regression for live ordinary passives with obsolete skill-point metadata.

Uses exact current tree/learning fields without needing the binary asset pack.
Real catalog plus town/dungeon encoding qualification is recorded separately.
"""
from pathlib import Path
import importlib.util,json,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'references/native-modern-auto-learning-20261027-v1'

class ModernAutoLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((SOURCE/'learning-metadata-fixture.json').read_bytes())
        spec=importlib.util.spec_from_file_location('ordinary_learning_candidate',SOURCE/'shared/els_server/domain/skill_rules.py')
        cls.rules=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.rules)

    def learned(self,unit_class,level=99,unsealed=()):
        data=self.data
        class Definitions:
            def skill_tree(self,c):return data['trees'][str(c)]
            def skill(self,s):return data['skills'][str(s)]
        role=dict(unit_class=unit_class,level=level,transcendence=unit_class in(125,173),master=False)
        with patch.object(self.rules,'client_data',return_value=Definitions()), \
             patch('els_server.domain.skill_unlocks.unsealed_skills',return_value=unsealed), \
             patch('els_server.domain.role_progression.first_master_skill',return_value=0), \
             patch('els_server.domain.role_progression.master_skills',return_value=()):
            return self.rules.learned_skills(role)

    def test_live_passives_with_old_SP_fields_are_not_lost(self):
        for c in (125,173):
            result=self.learned(c,unsealed=(28414,))
            for sid in (28410,28411,28413,28414,28429):
                with self.subTest(unit_class=c,skill=sid):self.assertEqual(result[sid],4)
        result=self.learned(35)
        self.assertEqual(result[28410],4);self.assertEqual(result[28429],4)
        self.assertFalse({28411,28413,28414}&set(result))

    def test_native_rank_boundaries(self):
        for level,rank in ((14,0),(15,1),(30,1),(31,2),(38,2),(39,3),(82,3),(83,4),(99,4)):
            with self.subTest(level=level):self.assertEqual(self.learned(35,level).get(28410,0),rank)
        for level,rank in ((34,0),(35,1),(50,1),(51,2),(58,2),(59,3),(91,3),(92,4)):
            with self.subTest(level=level):self.assertEqual(self.learned(125,level).get(28411,0),rank)

    def test_sealed_passive_still_requires_owned_unlock(self):
        self.assertNotIn(28414,self.learned(125))
        self.assertNotIn(28414,self.learned(173))
        self.assertNotIn(28414,self.learned(125,59,(28414,)))
        self.assertEqual(self.learned(125,60,(28414,))[28414],1)

    def test_no_other_character_or_relationship_grant(self):
        for c in (1,8):self.assertFalse({28410,28411,28413,28414,28429}&set(self.learned(c)))
        for c in (1,8,35,125,173):self.assertFalse({300,900,905,906}&set(self.learned(c)))

if __name__=='__main__':unittest.main()
