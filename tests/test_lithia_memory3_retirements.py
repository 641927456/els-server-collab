"""LITHIA_MEMORY3 (35270) scene dummies retire on the client's scene timeline.

Stage 0 declares only story dummies; its gate is the retirement of 9338. The
per-dummy epic quests (28230/28240/28250) only become active between runs, so
requiring them before accepting a retirement stranded stage 0 with no combat.
Quest credit still requires an active matching quest, so retiring without one
adds no progress.
"""
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import story_controller_retirements as target
from test_tunnel_native_retirements import fixture, OWNER

IDENTITIES=[(35270,0,0,9335,1),(35270,0,0,9337,3),(35270,0,0,9338,4),
            (35270,1,0,9339,1),(35270,1,1,9340,1),(35270,1,2,9341,1),
            (35270,1,2,9338,2),(35270,1,3,9341,1),(35270,1,3,9342,3)]
STAGE0_REQUIRED=(35270,0,0,9338,4)
UNIT=15

def identity(row):
    return tuple(row[k] for k in ('dungeon','stage','part','template'))+(row['source']['source_index'],)

def model_fixture(rule,*,quest=0):
    # No quest rows at all: the player entered through job quest 53680.
    session,event,report,store=fixture(rule,unit=UNIT,quest=quest)
    session.dungeon_run.identity=rule['dungeon']
    session.dungeon_run.stage=rule['stage']
    session.dungeon_run.part=rule['part']
    return session,event,report,store

class Memory3Retirements(unittest.TestCase):
    @property
    def rules(self):
        return [r for r in target.RULES if r['dungeon']==35270]

    def call(self,s,e,r,store,*,lease=True):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{
                'els_server.domain.dungeon_equipment_loot_flow':NS(current_lease=lambda actor:lease),
                'els_server.domain.quest_flow':NS(store=lambda actor:store),
                'els_server.domain.dungeon_flow':NS(periodic=lambda actor:[])}))
            return target.handle(s,e,r)

    def test_relaxation_is_declared_on_35270_only(self):
        self.assertEqual([identity(r) for r in self.rules],IDENTITIES)
        self.assertTrue(all(r.get('retire_without_quest') for r in self.rules))
        self.assertFalse([identity(r) for r in target.RULES
                          if r['dungeon']!=35270 and r.get('retire_without_quest')])

    def test_unearned_epic_quest_does_not_strand_scene_dummy(self):
        for rule in self.rules:
            with self.subTest(source=identity(rule)):
                s,e,r,store=model_fixture(rule)
                try:
                    self.assertEqual([x.kind for x in self.call(s,e,r,store)],[0xae,0xaf])
                    self.assertEqual(store.calls,1)
                    self.assertEqual(s.dungeon_run.defeated,{r['index']:e.payload})
                    self.assertFalse(s.part_end_notified)
                    self.assertEqual([x.kind for x in self.call(s,e,r,store)],[0xae])
                    self.assertEqual(store.calls,1)
                finally:store.db.close()

    def test_stage0_required_retirement_is_accepted(self):
        rule=next(r for r in self.rules if identity(r)==STAGE0_REQUIRED)
        s,e,r,store=model_fixture(rule)
        try:
            self.assertEqual([x.kind for x in self.call(s,e,r,store)],[0xae,0xaf])
            self.assertIn(rule['source']['source_index']-1,s.dungeon_run.defeated)
            self.assertFalse(s.clear_notified)
        finally:store.db.close()

    def test_source_owner_unit_hp_and_lease_checks_still_reject(self):
        rule=self.rules[0]
        for change in ('source','owner','hp','unit','lease'):
            with self.subTest(change=change):
                s,e,r,store=model_fixture(rule)
                if change=='source':s.dungeon_run.current['npcs'][0]['points']=[999999]
                if change=='owner':r['readiness']={OWNER+1:0}
                if change=='hp':r['hp_bits']=0
                if change=='unit':s.account.character=lambda:{'unit_type':16,'level':99}
                try:
                    self.assertEqual(self.call(s,e,r,store,lease=change!='lease'),[])
                    self.assertFalse(s.dungeon_run.defeated)
                    self.assertEqual(store.calls,0)
                finally:store.db.close()

if __name__=='__main__':unittest.main()
