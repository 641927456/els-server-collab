"""Source admission only; original client AI/waves have separate evidence."""
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
    """Exercise validate/prepare; not a substitute for actual storage/TLS."""
    def __init__(self,quest=26650):
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


def fixture(unit=14,quest=26650):
    rule=next(r for r in target.RULES if(r['dungeon'],r['stage'],r['part'],r['template'])==(34320,1,1,7523))
    actor={**copy.deepcopy(rule['source']),'key':0,'hp':rule['hp'],'start_point':23}
    hostile={'key':9,'template':7509,'source_index':10,'active':True,'team':1}
    graph={'source_sha256':rule['graph_sha']}
    catalog=NS(graph=lambda identity:graph,manifest={'source_sha256':{rule['script']:rule['script_sha']}})
    run=NS(identity=34320,run_id='owned-static-source',stage=1,part=1,current={'npcs':[actor,hostile]},
           graph=graph,catalog=catalog,defeated={},next=None,ready_at=None)
    session=NS(dungeon_run=run,account=NS(uid=OWNER,character=lambda:{'unit_type':unit,'level':99}),
               role='game',phase='dungeon_active',dungeon_substage_synced=True,clear_notified=False,
               reward_transaction=None,reward_run_id=run.run_id,dungeon_participants=(OWNER,),
               dungeon_clock=NS(total=0,started=1),part_end_notified=False,defeated_npcs=run.defeated)
    report=dict(index=0,flag=255,status=1,source=MAX_UID,killer=MAX_UID,extra_uid=0,last_uid=0,
                contribution={},counters={},readiness={OWNER:0},xyz=(0.,)*6,
                hp_bits=struct.unpack('>I',struct.pack('>f',rule['hp']))[0])
    event=Event(0x202,kind=0xad,performers=(0,),payload=b'original-source-admission-fixture')
    return session,event,report,WitnessStore(quest)


class SharedStaticRetirement(unittest.TestCase):
    def call(self,s,e,r,store,lease=True):
        with ExitStack()as stack:
            stack.enter_context(patch.dict(sys.modules,{
                'els_server.domain.dungeon_equipment_loot_flow':NS(current_lease=lambda actor:lease),
                'els_server.domain.quest_flow':NS(store=lambda actor:store),
                'els_server.domain.dungeon_flow':NS(periodic=lambda actor:[])}))
            return target.handle(s,e,r)

    def test_exact_one_source_and_original_common_map_qualification(self):
        rows=[r for r in target.RULES if r['dungeon']==34320]
        self.assertEqual(len(rows),1)
        r=rows[0]
        self.assertEqual((r['stage'],r['part'],r['template'],r['source']['source_index'],r['source']['points']),(1,1,7523,1,[23]))
        self.assertEqual(r['units'],list(range(1,16)))
        self.assertEqual(r['map_quests'],[26650])
        self.assertEqual(r['quests'],[])
        self.assertTrue(r['source']['active']and r['source']['no_drop']and r['requires_native_255'])

    def test_all_original_units_and_real_zero_slot_retire_once_without_other_deaths(self):
        for unit in range(1,16):
            with self.subTest(unit=unit):
                s,e,r,store=fixture(unit)
                try:
                    self.assertEqual([x.kind for x in self.call(s,e,r,store)],[0xae,0xaf])
                    self.assertEqual([x.kind for x in self.call(s,e,r,store)],[0xae])
                    self.assertEqual(store.calls,1)
                    self.assertEqual(set(s.dungeon_run.defeated),{0})
                    self.assertNotIn(9,s.dungeon_run.defeated)
                    self.assertFalse(s.clear_notified or s.part_end_notified)
                    self.assertEqual((s.dungeon_run.stage,s.dungeon_run.part),(1,1))
                finally:store.db.close()

    def test_ordinary_combat_is_denied_only_for_this_static_source(self):
        for flag in(0,1):
            s,e,r,store=fixture();r['flag']=flag
            try:
                self.assertEqual(self.call(s,e,r,store),[])
                self.assertFalse(s.dungeon_run.defeated)
                self.assertEqual(store.calls,0)
                r['index']=9
                self.assertIsNone(self.call(s,e,r,store))
            finally:store.db.close()

    def test_wrong_origin_or_unearned_region_cannot_retire(self):
        for change in('map','stage','part','source','point','graph','script','hp','owner','unit','region','only_story22630','instance','dynamic'):
            with self.subTest(change=change):
                s,e,r,store=fixture(unit=16 if change=='unit'else 14,quest=0 if change=='region'else 22630 if change=='only_story22630'else 26650)
                actor=s.dungeon_run.current['npcs'][0]
                if change=='map':s.dungeon_run.identity=34321
                if change=='stage':s.dungeon_run.stage=0
                if change=='part':s.dungeon_run.part=0
                if change=='source':actor['source_index']=2
                if change=='point':actor['start_point']=24
                if change=='graph':s.dungeon_run.graph={'source_sha256':'wrong'}
                if change=='script':s.dungeon_run.catalog.manifest={'source_sha256':{}}
                if change=='hp':r['hp_bits']=0
                if change=='owner':r['readiness']={OWNER+1:0}
                if change=='instance':r['index']=999
                if change=='dynamic':actor['dynamic']=True
                try:
                    self.assertFalse(self.call(s,e,r,store))
                    self.assertFalse(s.dungeon_run.defeated)
                    self.assertFalse(s.clear_notified or s.part_end_notified)
                finally:store.db.close()

    def test_lease_party_and_reward_scope_remain_enforced(self):
        for change in('lease','party','reward'):
            s,e,r,store=fixture()
            if change=='party':s.dungeon_participants=(OWNER,OWNER+1)
            if change=='reward':s.reward_transaction=object()
            try:
                self.assertEqual(self.call(s,e,r,store,lease=change!='lease'),[])
                self.assertFalse(s.dungeon_run.defeated)
                self.assertEqual(store.calls,0)
            finally:store.db.close()

    def test_prepare_failure_cannot_commit_in_memory_retirement(self):
        s,e,r,store=fixture();store.fail_prepare=True
        try:
            with self.assertRaisesRegex(RuntimeError,'controlled encode failure'):self.call(s,e,r,store)
            self.assertFalse(s.dungeon_run.defeated)
            self.assertFalse(s.part_end_notified)
        finally:store.db.close()


if __name__=='__main__':unittest.main()
