"""Finite tunnel retirement admission; natural client waves are separate evidence."""
import copy
import sqlite3
import struct
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import story_controller_retirements as target
from els_server.protocol.protocol_codec import Event

OWNER=1001
MAX_UID=2**64-1


class WitnessStore:
    """Only the handler's validate/prepare callback contract is exercised here.

    Actual storage atomicity, full TLS and rollback have separate runtime proof;
    this small fixture never claims to reproduce those storage implementations.
    """
    def __init__(self,quest):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE completed_quests(owner,quest)')
        self.db.execute('CREATE TABLE character_quests(owner,quest)')
        if quest:self.db.execute('INSERT INTO completed_quests VALUES (?,?)',(OWNER,quest))
        self.calls=0
        self.fail_prepare=False

    def record(self,key,witness,payload,*,validate,prepare):
        self.calls+=1
        validate(self.db)
        if self.fail_prepare:raise RuntimeError('controlled encode failure')
        return prepare([],False)


def fixture(rule,unit=13,quest=26640):
    actor={**copy.deepcopy(rule['source']),'key':rule['source']['source_index']-1,
           'hp':rule['hp'],'start_point':rule['source']['points'][0]}
    door={'key':99,'template':6212,'source_index':100,'active':True,'team':1}
    graph={'source_sha256':rule['graph_sha']}
    catalog=NS(graph=lambda identity:graph,manifest={'source_sha256':{rule['script']:rule['script_sha']}})
    run=NS(identity=34060,run_id='owned-tunnel-test',stage=1,part=0,
           current={'npcs':[actor,door]},graph=graph,catalog=catalog,
           defeated={},next=None,ready_at=None)
    session=NS(dungeon_run=run,account=NS(uid=OWNER,character=lambda:{'unit_type':unit,'level':99}),
               role='game',phase='dungeon_active',dungeon_substage_synced=True,clear_notified=False,
               reward_transaction=None,reward_run_id=run.run_id,dungeon_participants=(OWNER,),
               dungeon_clock=NS(total=0,started=1),part_end_notified=False,defeated_npcs=run.defeated)
    report=dict(index=actor['key'],flag=255,status=1,source=MAX_UID,killer=MAX_UID,
                extra_uid=0,last_uid=0,contribution={},counters={},readiness={OWNER:0},
                xyz=(0.,)*6,hp_bits=struct.unpack('>I',struct.pack('>f',rule['hp']))[0])
    event=Event(0x202,kind=0xad,performers=(0,),payload=b'canonical-admission-fixture')
    return session,event,report,WitnessStore(quest)


class TunnelRetirement(unittest.TestCase):
    @property
    def rules(self):return [r for r in target.RULES if r['dungeon']==34060]

    def call(self,s,e,r,store):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{
                'els_server.domain.dungeon_equipment_loot_flow':NS(current_lease=lambda actor:True),
                'els_server.domain.quest_flow':NS(store=lambda actor:store),
                'els_server.domain.dungeon_flow':NS(periodic=lambda actor:[])}))
            return target.handle(s,e,r)

    def test_only_two_original_summoners_are_registered(self):
        self.assertEqual([(r['stage'],r['part'],r['template'],r['source']['source_index'])for r in self.rules],
                         [(1,0,6203,2),(1,0,6214,3)])
        self.assertTrue(all(r['requires_native_255']for r in self.rules))

    def test_original_retirement_and_same_payload_retry_preserve_door(self):
        for rule in self.rules:
            for unit in (1,13,14,15):
                with self.subTest(template=rule['template'],unit=unit):
                    s,e,r,store=fixture(rule,unit)
                    try:
                        self.assertEqual([x.kind for x in self.call(s,e,r,store)],[0xae,0xaf])
                        self.assertEqual([x.kind for x in self.call(s,e,r,store)],[0xae])
                        self.assertEqual(store.calls,1)
                        self.assertEqual(set(s.dungeon_run.defeated),{r['index']})
                        self.assertNotIn(99,s.dungeon_run.defeated)
                        self.assertFalse(s.clear_notified)
                        self.assertFalse(s.part_end_notified)
                    finally:store.db.close()

    def test_ordinary_combat_cannot_consume_invulnerable_source(self):
        for rule in self.rules:
            for flag in (0,1):
                with self.subTest(template=rule['template'],flag=flag):
                    s,e,r,store=fixture(rule);r['flag']=flag
                    try:
                        self.assertEqual(self.call(s,e,r,store),[])
                        self.assertFalse(s.dungeon_run.defeated)
                        self.assertEqual(store.calls,0)
                        r['index']=99
                        self.assertIsNone(self.call(s,e,r,store))
                    finally:store.db.close()

    def test_wrong_native_source_and_unearned_quest_do_not_retire(self):
        for change in ('hp','owner','instance','stage','quest','unit'):
            with self.subTest(change=change):
                s,e,r,store=fixture(self.rules[0],unit=16 if change=='unit'else 13,
                                    quest=0 if change=='quest'else 26640)
                if change=='hp':r['hp_bits']=0
                if change=='owner':r['readiness']={OWNER+1:0}
                if change=='instance':r['index']=888
                if change=='stage':s.dungeon_run.stage=0
                try:
                    self.assertEqual(self.call(s,e,r,store),[])
                    self.assertFalse(s.dungeon_run.defeated)
                    self.assertFalse(s.clear_notified)
                finally:store.db.close()

    def test_prepare_failure_never_commits_in_memory_retirement(self):
        s,e,r,store=fixture(self.rules[0]);store.fail_prepare=True
        try:
            with self.assertRaisesRegex(RuntimeError,'controlled encode failure'):
                self.call(s,e,r,store)
            self.assertFalse(s.dungeon_run.defeated)
            self.assertFalse(s.part_end_notified)
        finally:store.db.close()


if __name__=='__main__':unittest.main()
