"""Memory1 keeps the accepted real 9470 witness and its original quest barrier."""
import unittest
from unittest.mock import patch
from els_server.domain import lithia_memory1_retirements as target
from els_server.domain.dungeon_lifecycle import death_report
from els_server.domain.seal_quests import quest_catalog
from els_server.domain.tutorial_dialogue import inactive_increment
from test_tunnel_native_retirements import WitnessStore
from test_lithia_memory8_offfield_expiry import OWNER,run_stage,session,event_for

class CapturedStore(WitnessStore):
    def __init__(self):
        super().__init__(28100)
        self.db.execute('ALTER TABLE character_quests ADD COLUMN objectives TEXT')
        self.db.execute('INSERT INTO character_quests VALUES (?,?,?)',(OWNER,28110,'{"28110":0}'))
        self.witnesses=[]
    def record(self,key,witness,payload,**kw):
        self.witnesses.append(witness)
        return super().record(key,witness,payload,**kw)

def fixture():
    run=run_stage(1,0,35250)
    return session(run,part_end_notified=False),CapturedStore()

def call(s,key,state):
    e=event_for(s.dungeon_run,key)
    with patch('els_server.domain.quest_flow.store',return_value=state):return target.handle(s,e,death_report(e.payload))

class Stage1Barrier(unittest.TestCase):
    def test_9310_never_fabricates_unreported_9470_or_its_quest_credit(self):
        s,state=fixture()
        try:
            self.assertEqual([e.kind for e in call(s,2,state)],[0xae,0xaf])
            self.assertEqual(set(s.dungeon_run.defeated),{2})
            self.assertEqual(s.dungeon_run.memory1_quest_barrier,frozenset((1,)))
            self.assertFalse(s.part_end_notified)
            self.assertEqual((state.witnesses[0]['kind'],state.witnesses[0]['npc']),('kill',9310))
            self.assertNotIn('tutorial_quest',state.witnesses[0])
            self.assertEqual([e.kind for e in call(s,2,state)],[0xae]);self.assertEqual(state.calls,1)
        finally:state.db.close()

    def test_only_real_9470_report_unblocks_the_pending_gate(self):
        s,state=fixture()
        try:
            call(s,2,state)
            self.assertEqual([e.kind for e in call(s,1,state)],[0xae,0xaf,0xba])
            self.assertTrue(s.part_end_notified);self.assertEqual(set(s.dungeon_run.defeated),{1,2})
            self.assertEqual((state.witnesses[1]['kind'],state.witnesses[1]['npc'],state.witnesses[1]['tutorial_quest']),('kill',9470,28110))
            self.assertEqual([e.kind for e in call(s,1,state)],[0xae]);self.assertEqual(state.calls,2)
        finally:state.db.close()

    def test_real_9470_first_waits_for_9310(self):
        s,state=fixture()
        try:
            self.assertEqual([e.kind for e in call(s,1,state)],[0xae,0xaf])
            self.assertFalse(s.part_end_notified)
            self.assertEqual([e.kind for e in call(s,2,state)],[0xae,0xaf,0xba])
        finally:state.db.close()

    def test_missing_earned_predecessor_rejects(self):
        s,state=fixture();state.db.execute('DELETE FROM completed_quests')
        try:
            self.assertEqual(call(s,2,state),[]);self.assertEqual(call(s,1,state),[])
            self.assertFalse(s.dungeon_run.defeated);self.assertFalse(s.part_end_notified)
        finally:state.db.close()

    def test_28110_only_consumes_its_real_kill_witness(self):
        sub=quest_catalog().objectives(28110)[0]
        witness=dict(kind='retire',dungeon=35250,npc=9470,tutorial_quest=28110,retired_by=9310)
        self.assertEqual(inactive_increment(sub,witness),0)
        self.assertEqual(inactive_increment(sub,{**witness,'kind':'kill'}),1)
        self.assertEqual(inactive_increment(sub,{**witness,'kind':'kill','npc':9310}),0)

if __name__=='__main__':unittest.main()
