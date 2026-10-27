"""Keep the accepted formal quest gates; no blanket quest-free retirement."""
import unittest
from els_server.domain import story_controller_retirements as target
from test_lithia_memory8_retirements import fixture,call

class ExistingFormalRetirements(unittest.TestCase):
    def test_each_original_source_keeps_its_quest_gate(self):
        rules=[r for r in target.RULES if r['dungeon']==35270]
        self.assertTrue(rules)
        for rule in rules:
            self.assertFalse(rule.get('retire_without_quest'))
            for quest,accepted in ((0,False),((rule['quests'] or rule['map_quests'])[0],True)):
                with self.subTest(template=rule['template'],stage=rule['stage'],part=rule['part'],quest=quest):
                    s,e,r,state=fixture(rule,quest)
                    try:
                        reply=call(s,e,r,state)
                        self.assertEqual([x.kind for x in reply],[0xae,0xaf] if accepted else [])
                        self.assertEqual(bool(s.dungeon_run.defeated),accepted)
                    finally:state.db.close()

if __name__=='__main__':unittest.main()
