"""The native event button uses class0 for transcendence, not current class."""
import unittest

from els_server.domain.careers import PARENTS,RULES
from els_server.domain.character_rules import CLASSES
from els_server.domain.quick_start import QUESTS,career_transition
from els_server.game_data import client_data
from els_server.storage.characters import DEFAULT_CHARACTER


class NativeQuickStartContract(unittest.TestCase):
    def test_native_zero_across_every_second_class(self):
        routes=[cls for cls,row in CLASSES.items() if row['stage']==2]
        self.assertEqual(len(routes),60)
        for cls in routes:
            with self.subTest(cls=cls):
                before=dict(DEFAULT_CHARACTER,unit_class=cls,
                    unit_type=client_data().unit(cls)['unitType'],level=70,
                    transcendence=False,master=False,artifact=None)
                after=career_transition(before,0,{QUESTS[2]})
                self.assertTrue(after['transcendence'])
                self.assertEqual(after['unit_class'],cls)
                for actor,completed in ((before,set()),(dict(before,level=69),{QUESTS[2]})):
                    with self.assertRaises(ValueError):career_transition(actor,0,completed)
                with self.assertRaises(ValueError):career_transition(after,0,{QUESTS[2]})

    def test_selected_advancement_class_is_preserved(self):
        promotions=[r for r in RULES.values() if r['kind'].startswith('advancement_')]
        self.assertEqual(len(promotions),180)
        for rule in promotions:
            with self.subTest(target=rule['target']):
                stage=int(rule['kind'][-1])-1
                before=dict(DEFAULT_CHARACTER,unit_class=PARENTS[rule['target']],
                    unit_type=rule['unit_type'],level=99,transcendence=stage==2,
                    master=False,artifact=None)
                after=career_transition(before,rule['target'],{QUESTS[(0,1,3)[stage]]})
                self.assertEqual(after['unit_class'],rule['target'])
                with self.assertRaises(ValueError):career_transition(before,rule['target'],set())


if __name__=='__main__':unittest.main()
