"""Finite Memory2 candidate against current graphs, with synthetic wire reports.

These are offline protocol/atomicity checks, not natural client scene evidence.
"""
import copy
import struct
import unittest
from unittest.mock import patch
from els_server.domain import scene_actor_retirements as target
from els_server.domain.dungeon_lifecycle import death_report
from els_server.protocol.protocol_codec import Event
from test_lithia_memory8_offfield_expiry import run_stage,actor,session,native255,OWNER


def fixture(key=12):
    run=run_stage(0,1,35260);s=session(run,part_end_notified=False)
    e=Event(0x202,performers=(0,),kind=0xad,payload=native255(key,actor(run,key)['hp']))
    return s,e,death_report(e.payload)


def call(s,e,r):
    with patch.object(target,'SCENE_ACTOR_RETIREMENTS_ENABLED',True):return target.handle(s,e,r)


class FiniteSceneRetirements(unittest.TestCase):
    def test_candidate_is_off_until_native_producer_qualification(self):
        s,e,r=fixture()
        self.assertFalse(target.SCENE_ACTOR_RETIREMENTS_ENABLED)
        self.assertIsNone(target.handle(s,e,r));self.assertFalse(s.dungeon_run.defeated)

    def test_all_six_original_sources_use_current_formal_hp_without_rewards(self):
        for key,(index,point) in target.FLOWER_SOURCES.items():
            with self.subTest(source=index):
                s,e,r=fixture(key);run=s.dungeon_run;npc=actor(run,key)
                self.assertEqual((npc['template'],npc['source_index'],npc['start_point']),(9323,index,point))
                self.assertEqual(npc['hp'],30203.0)
                with patch('els_server.domain.quest_flow.store') as q,patch('els_server.domain.dungeon_equipment_loot_flow.accepted_death') as loot,patch('els_server.domain.legacy_pve_exp.accepted_death') as xp:
                    self.assertEqual([x.kind for x in call(s,e,r)],[0xae,0xaf])
                    self.assertEqual([x.kind for x in call(s,e,r)],[0xae])
                    q.assert_not_called();loot.assert_not_called();xp.assert_not_called()
                self.assertEqual(run.defeated,{key:e.payload});self.assertFalse(npc['active'])
                self.assertFalse(s.clear_notified);self.assertFalse(s.world_drops)
                self.assertIsNone(run.next);self.assertFalse(s.part_end_notified)

    def test_flowers_do_not_replace_gate9324_or_create_unreported_actors(self):
        s,e,r=fixture();run=s.dungeon_run;before=copy.deepcopy(run.current['npcs'])
        for key in target.FLOWER_SOURCES:
            body=native255(key,actor(run,key)['hp']);e=Event(0x202,performers=(0,),kind=0xad,payload=body)
            self.assertEqual([x.kind for x in call(s,e,death_report(body))],[0xae,0xaf])
        self.assertEqual(run.current['conditions'][0]['required'],[9324])
        self.assertFalse(run.condition_ready(run.current['conditions'][0]));self.assertIsNone(run.next)
        self.assertTrue(actor(run,18)['active']);self.assertNotIn(18,run.defeated)
        self.assertEqual(len(run.current['npcs']),len(before))
        self.assertFalse(any(n.get('dynamic') for n in run.current['npcs']))

    def test_existing_accepted_gate_can_progress_only_after_original_reports(self):
        s,e,r=fixture();run=s.dungeon_run
        run.defeated[18]=b'separate accepted original9324 report'
        self.assertEqual([x.kind for x in call(s,e,r)],[0xae,0xaf,0xba])
        self.assertEqual((run.next['stage'],run.next['part']),(0,2));self.assertTrue(s.part_end_notified)
        self.assertFalse(s.clear_notified)

    def test_encoder_failure_preserves_all_actor_gate_clock_and_drop_state(self):
        s,e,r=fixture();run=s.dungeon_run;run.defeated[18]=b'accepted gate'
        before=(copy.deepcopy(run.current),dict(run.defeated),run.next,run.ready_at,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started,dict(s.world_drops))
        count=[0]
        from els_server.protocol.protocol_codec import encode_event
        def fail_last(reply):
            count[0]+=1
            if reply.kind==0xba:raise RuntimeError('controlled final reply failure')
            return encode_event(reply)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=fail_last):
            with self.assertRaisesRegex(RuntimeError,'controlled final reply failure'):call(s,e,r)
        self.assertEqual(count[0],3)
        self.assertEqual((run.current,run.defeated,run.next,run.ready_at,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started,s.world_drops),before)

    def test_source_identity_and_session_poisoning_rejects(self):
        changes=('source','point','template','active','team','ally','boss','no_drop','graph','graph_content','script','instance_hp','report_hp','owner','unit','lease','generation','phase','participants','transaction','performers','uid','duplicate')
        for change in changes:
            with self.subTest(change=change):
                s,e,r=fixture();run=s.dungeon_run;npc=actor(run,12)
                if change=='source':npc['source_index']=2
                if change=='point':npc['start_point']=11
                if change=='template':npc['template']=9324
                if change in ('active','team','ally','boss','no_drop'):npc[change]={'active':False,'team':0,'ally':True,'boss':True,'no_drop':True}[change]
                if change=='graph':run.graph['source_sha256']='0'*64
                if change=='graph_content':run.graph['stages']['0']['parts']['1']['conditions'][0]['required']=[9323]
                if change=='script':run.catalog=copy.copy(run.catalog);run.catalog.manifest=copy.deepcopy(run.catalog.manifest);run.catalog.manifest['source_sha256'][target.SCRIPT]='0'*64
                if change=='instance_hp':npc['hp']+=1
                if change=='report_hp':r['hp_bits']=struct.unpack('>I',struct.pack('>f',5000))[0]
                if change=='owner':r['readiness']={OWNER+1:0}
                if change=='unit':s.account.character=lambda:{'unit_type':16,'level':70}
                if change=='lease':s.application.playing[71]=object()
                if change=='generation':s.reward_run_id='other'
                if change=='phase':s.phase='town_ready'
                if change=='participants':s.dungeon_participants=frozenset((OWNER,OWNER+1))
                if change=='transaction':s.reward_transaction=object()
                if change=='performers':e=Event(0x202,performers=(1,),kind=0xad,payload=e.payload)
                if change=='uid':e=Event(0x202,performers=(0,),kind=0xad,payload=e.payload,uid=OWNER)
                if change=='duplicate':run.current['npcs'].append(dict(npc))
                self.assertEqual(call(s,e,r),[]);self.assertFalse(run.defeated)

    def test_native_shape_is_required_and_conflicting_replay_rejected(self):
        for name,value in (('flag',0),('status',0),('source',OWNER),('killer',OWNER),('last_uid',1),('extra_uid',1),('contribution',{OWNER:1.}),('counters',{OWNER:1})):
            s,e,r=fixture();r[name]=value
            self.assertEqual(call(s,e,r),[]);self.assertFalse(s.dungeon_run.defeated)
        s,e,r=fixture();call(s,e,r)
        raw=bytearray(e.payload);struct.pack_into('>f',raw,21,1.)
        e2=Event(0x202,performers=(0,),kind=0xad,payload=bytes(raw))
        self.assertEqual(call(s,e2,death_report(e2.payload)),[])
        self.assertEqual(s.dungeon_run.defeated,{12:e.payload})

    def test_other_scenes_gates_combat_and_dynamic_actors_are_not_admitted(self):
        s,e,r=fixture(18);self.assertIsNone(call(s,e,r))
        s,e,r=fixture();actor(s.dungeon_run,12)['dynamic']=True
        self.assertIsNone(call(s,e,r));self.assertFalse(s.dungeon_run.defeated)
        for dungeon in (35261,35270,35320):
            run=run_stage(0,0,dungeon);s=session(run)
            self.assertIsNone(call(s,e,r));self.assertFalse(run.defeated)


if __name__=='__main__':unittest.main()
