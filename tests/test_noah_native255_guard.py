"""Exact native255 admission; resource-free callback model, not natural gameplay."""
from dataclasses import replace
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import story_controller_retirements as target
from test_tunnel_native_retirements import fixture, OWNER

IDENTITIES = [(34620, 0, 0, 8058, 3), (34680, 0, 0, 8142, 9)]
UNIT = 14

def identity(row):
    return tuple(row[k] for k in ('dungeon','stage','part','template'))+(row['source']['source_index'],)

def model_fixture(rule, *, quest=True):
    # Only an in-memory model is parameterized; this never mutates a real run.
    earned=(rule['quests'] or rule['map_quests'])[0] if quest else 0
    session,event,report,store=fixture(rule,unit=UNIT,quest=earned)
    session.dungeon_run.identity=rule['dungeon']
    session.dungeon_run.stage=rule['stage']
    session.dungeon_run.part=rule['part']
    return session,event,report,store

class Native255Guard(unittest.TestCase):
    @property
    def rules(self):
        return [r for r in target.RULES if identity(r) in IDENTITIES]

    def call(self,s,e,r,store,*,lease=True):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{
                'els_server.domain.dungeon_equipment_loot_flow':NS(current_lease=lambda actor:lease),
                'els_server.domain.quest_flow':NS(store=lambda actor:store),
                'els_server.domain.dungeon_flow':NS(periodic=lambda actor:[])}))
            return target.handle(s,e,r)

    def test_exact_existing_sources_have_native_guard(self):
        self.assertEqual([identity(r) for r in self.rules],IDENTITIES)
        self.assertTrue(all(r['requires_native_255'] is True for r in self.rules))

    def test_valid_native255_and_same_payload_retry_remain_accepted(self):
        for rule in self.rules:
            with self.subTest(source=identity(rule)):
                s,e,r,store=model_fixture(rule)
                try:
                    self.assertEqual([x.kind for x in self.call(s,e,r,store)],[0xae,0xaf])
                    self.assertEqual([x.kind for x in self.call(s,e,r,store)],[0xae])
                    self.assertEqual(store.calls,1)
                    self.assertEqual(s.dungeon_run.defeated,{r['index']:e.payload})
                    self.assertNotIn(99,s.dungeon_run.defeated)
                    self.assertFalse(s.clear_notified)
                    self.assertFalse(s.part_end_notified)
                    changed=replace(e,payload=b'changed-fixture-payload')
                    self.assertEqual(self.call(s,changed,r,store),[])
                    self.assertEqual(store.calls,1)
                finally:store.db.close()

    def test_ordinary0_and1_rejected_without_consuming_instance(self):
        for rule in self.rules:
            for flag in (0,1):
                with self.subTest(source=identity(rule),flag=flag):
                    s,e,r,store=model_fixture(rule);r['flag']=flag
                    try:
                        self.assertEqual(self.call(s,e,r,store),[])
                        self.assertFalse(s.dungeon_run.defeated)
                        self.assertEqual(store.calls,0)
                        # A different current actor remains owned by generic combat.
                        r['index']=99
                        self.assertIsNone(self.call(s,e,r,store))
                    finally:store.db.close()

    def test_wrong_source_owner_quest_hp_unit_or_lease_rejected(self):
        for rule in self.rules:
            for change in ('source','owner','quest','hp','unit','lease'):
                with self.subTest(source=identity(rule),change=change):
                    s,e,r,store=model_fixture(rule,quest=change!='quest')
                    if change=='source':s.dungeon_run.current['npcs'][0]['points']=[999999]
                    if change=='owner':r['readiness']={OWNER+1:0}
                    if change=='hp':r['hp_bits']=0
                    if change=='unit':s.account.character=lambda:{'unit_type':16,'level':99}
                    try:
                        self.assertEqual(self.call(s,e,r,store,lease=change!='lease'),[])
                        self.assertFalse(s.dungeon_run.defeated)
                        self.assertFalse(s.clear_notified)
                        self.assertFalse(s.part_end_notified)
                    finally:store.db.close()

    def test_callback_failure_preserves_in_memory_retirement(self):
        for rule in self.rules:
            with self.subTest(source=identity(rule)):
                s,e,r,store=model_fixture(rule);store.fail_prepare=True
                try:
                    with self.assertRaisesRegex(RuntimeError,'controlled encode failure'):
                        self.call(s,e,r,store)
                    self.assertFalse(s.dungeon_run.defeated)
                    self.assertFalse(s.clear_notified)
                    self.assertFalse(s.part_end_notified)
                finally:store.db.close()

if __name__=='__main__':unittest.main()
