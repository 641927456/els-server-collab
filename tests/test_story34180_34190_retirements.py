"""Exact native255 admission; resource-free callback model, not natural gameplay."""
from dataclasses import replace
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import story_controller_retirements as target
from test_tunnel_native_retirements import fixture, OWNER

IDENTITIES = [(34180, 0, 0, 7164, 8), (34180, 1, 0, 7166, 3), (34180, 2, 0, 7168, 3), (34190, 2, 0, 7204, 5)]
UNIT = 1

def identity(row):
    return tuple(row[k] for k in ('dungeon','stage','part','template'))+(row['source']['source_index'],)

def model_fixture(rule, *, quest=True):
    # Only an in-memory model is parameterized; this never mutates a real run.
    earned=(rule['quests'] or rule['map_quests'])[0] if quest else 0
    session,event,report,store=fixture(rule,unit=UNIT,quest=earned)
    session.dungeon_run.identity=rule['dungeon']
    session.dungeon_run.stage=rule['stage']
    session.dungeon_run.part=rule['part']
    if rule.get('requires_no_active_hostiles'):
        # Satisfy the existing predicate in this model; do not remove its guard.
        session.dungeon_run.current['npcs'][1]['active']=False
    return session,event,report,store

class SourceRetirementAdmission(unittest.TestCase):
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
        self.assertTrue(all(r['units']==list(range(1,13)) for r in self.rules))
        self.assertTrue(all(26650 not in r['map_quests'] and 25520 not in r['map_quests'] for r in self.rules))

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

    def test_original_no_active_hostile_predicate_still_required(self):
        for rule in self.rules:
            if not rule.get('requires_no_active_hostiles'):continue
            s,e,r,store=model_fixture(rule)
            s.dungeon_run.current['npcs'][1]['active']=True
            try:
                self.assertEqual(self.call(s,e,r,store),[])
                self.assertFalse(s.dungeon_run.defeated)
                self.assertEqual(store.calls,0)
            finally:store.db.close()

    def test_common_roles_and_common_quest_are_not_added_by_this_port(self):
        for rule in self.rules:
            for unit in (13,14,15):
                s,e,r,store=model_fixture(rule)
                s.account.character=lambda unit=unit:{'unit_type':unit,'level':99}
                try:
                    self.assertEqual(self.call(s,e,r,store),[])
                    self.assertFalse(s.dungeon_run.defeated)
                finally:store.db.close()
            s,e,r,store=model_fixture(rule,quest=False)
            store.db.execute('INSERT INTO completed_quests VALUES (?,?)',(OWNER,26650))
            try:
                self.assertEqual(self.call(s,e,r,store),[])
                self.assertFalse(s.dungeon_run.defeated)
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
