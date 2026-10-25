"""Code-first recovery disables new admissions and preserves original readers."""
import unittest
from unittest.mock import patch
from els_server.domain import dungeon_flow
from els_server.domain import story_controller_retirements as story
from els_server.domain.dungeon_lifecycle import death_report
from test_lithia_memory8_offfield_expiry import SOURCES,actor,run_stage,session,event_for
from test_lithia_memory8_retirements import fixture,call
from test_scene_actor_native_expiry import npc,fixture as scene_fixture,call as scene_call,native255
from els_server.protocol.protocol_codec import Event

class RetirementRecovery(unittest.TestCase):
    def test_production_constants_are_true(self):
        self.assertIs(dungeon_flow.MEMORY8_SOURCE_ACTOR_EXPIRY_ENABLED,True)
        self.assertIs(story.MEMORY8_9450_MAP_QUEST_ADMISSION_ENABLED,True)

    def test_source_flag_false_returns_to_parent_rejection_for_all_three(self):
        with patch.object(dungeon_flow,'MEMORY8_SOURCE_ACTOR_EXPIRY_ENABLED',False):
            for stage,part,key in SOURCES:
                with self.subTest(source=(stage,part,key)):
                    run=run_stage(stage,part);s=session(run);e=event_for(run,key)
                    self.assertIsNone(dungeon_flow.source_actor_expiry(s,e,death_report(e.payload)))
                    self.assertEqual(dungeon_flow.handle(s,e),[])
                    self.assertFalse(run.defeated);self.assertTrue(actor(run,key)['active'])
                    self.assertIsNone(run.next);self.assertIsNone(run.ready_at)

    def test_9450_flag_false_restores_objective_gate_but_retains_original_objective(self):
        rules=[r for r in story.RULES if r['template']==9450 and r['dungeon'] in (35320,35321)]
        with patch.object(story,'MEMORY8_9450_MAP_QUEST_ADMISSION_ENABLED',False):
            for rule in rules:
                for quest,accepted in ((28540,False),(28550,True)):
                    with self.subTest(dungeon=rule['dungeon'],quest=quest):
                        s,e,r,state=fixture(rule,quest)
                        try:
                            reply=call(s,e,r,state)
                            self.assertEqual([x.kind for x in reply],[0xae,0xaf] if accepted else [])
                            self.assertEqual(bool(s.dungeon_run.defeated),accepted)
                        finally:state.db.close()

    def test_both_flags_false_preserve_original_dynamic_expiry(self):
        actor_=npc(12,9323,5000);actor_['dynamic']=True;s,run=scene_fixture(actor_)
        e=Event(0x202,performers=(0,),kind=0xad,payload=native255(12,5000))
        with patch.object(dungeon_flow,'MEMORY8_SOURCE_ACTOR_EXPIRY_ENABLED',False),patch.object(story,'MEMORY8_9450_MAP_QUEST_ADMISSION_ENABLED',False):
            self.assertEqual([x.kind for x in scene_call(s,e)],[0xae,0xaf])
            self.assertEqual([x.kind for x in scene_call(s,e)],[0xae])
        self.assertEqual(run.defeated,{12:e.payload})

    def test_9450_reader_keeps_identical_already_accepted_reply_after_recovery(self):
        rule=next(r for r in story.RULES if (r['dungeon'],r['template'])==(35320,9450))
        s,e,r,state=fixture(rule,28540)
        try:
            self.assertEqual([x.kind for x in call(s,e,r,state)],[0xae,0xaf])
            with patch.object(story,'MEMORY8_9450_MAP_QUEST_ADMISSION_ENABLED',False):
                self.assertEqual([x.kind for x in call(s,e,r,state)],[0xae])
            self.assertEqual(state.calls,1)
        finally:state.db.close()

if __name__=='__main__':unittest.main()
