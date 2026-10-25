"""Three observed Memory8 sources only; real resources, no player databases."""
import copy
import struct
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from els_server.domain import dungeon_flow
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.formal_npc_hp import initialized_maximum
from els_server.protocol.protocol_codec import Event

OWNER=1001
MAX_UID=2**64-1
SOURCES=((0,1,15),(0,1,17),(1,0,4))

def native255(key,hp,owner=OWNER,source=MAX_UID,killer=MAX_UID):
    return (struct.pack('>iBQQ6fBI',key,255,source,killer,0,0,0,0,0,0,1,
                        struct.unpack('>I',struct.pack('>f',float(hp)))[0])
            +struct.pack('>I',0)+struct.pack('>IQB',1,owner,0)+struct.pack('>Q',0)
            +struct.pack('>I',0)+struct.pack('>Q',0))

def run_stage(stage,part,dungeon=35320):
    run=DungeonRun(dungeon,'00000000-0000-4000-8000-000000000001')
    run._load_stage(stage);run.part=part;run.loaded()
    return run

def actor(run,key):return next(n for n in run.current['npcs'] if n['key']==key)

def session(run,*,part_end_notified=True):
    root=NS(character_accounts={})
    account=NS(uid=OWNER,account_id=71,root=root,store=NS(uid=OWNER),
               character=lambda:{'unit_type':15,'level':70})
    s=NS(dungeon_run=run,account=account,role='game',phase='dungeon_active',
         identity={'id':71},released=False,dungeon_substage_synced=True,
         clear_notified=False,part_end_notified=part_end_notified,
         dungeon_participants=frozenset((OWNER,)),reward_run_id=run.run_id,reward_transaction=None,
         reward_test=False,item_test=False,drop_probe=False,summon_keys=set(),
         defeated_npcs=run.defeated,world_drops={},world_drop_sequence=0,
         dungeon_clock=NS(total=0,started=1,pause=lambda:None))
    root.character_accounts[OWNER]=account
    s.application=NS(playing={71:s},accounts={71:root})
    return s

def event_for(run,key,**kw):
    return Event(0x202,performers=(0,),kind=0xad,payload=native255(key,actor(run,key)['hp'],**kw))

def gate(run):return {n['key'] for n in run.current['npcs'] if n['active'] and n.get('team',1)!=0}

class ObservedExpiry(unittest.TestCase):
    def test_current_formal_hp_and_all_three_original_instances(self):
        for stage,part,key in SOURCES:
            with self.subTest(source=(stage,part,key)):
                run=run_stage(stage,part);npc=actor(run,key);s=session(run);e=event_for(run,key)
                self.assertEqual(npc['hp'],initialized_maximum(run,npc))
                self.assertNotEqual(npc['hp'],500)
                with patch('els_server.domain.quest_flow.store') as quests,patch('els_server.domain.dungeon_equipment_loot_flow.accepted_death') as loot,patch('els_server.domain.legacy_pve_exp.accepted_death') as xp:
                    self.assertEqual([r.kind for r in dungeon_flow.handle(s,e)],[0xae,0xaf])
                    self.assertEqual([r.kind for r in dungeon_flow.handle(s,e)],[0xae])
                    quests.assert_not_called();loot.assert_not_called();xp.assert_not_called()
                self.assertEqual(run.defeated,{key:e.payload});self.assertFalse(npc['active'])
                self.assertFalse(s.clear_notified);self.assertFalse(s.world_drops)

    def test_each_gate_requires_the_original_remaining_actors(self):
        for stage,part,key in SOURCES:
            run=run_stage(stage,part);condition=run.current['conditions'][0]
            run.defeated=dict.fromkeys(gate(run)-{key},b'accepted-original-death')
            s=session(run,part_end_notified=False)
            self.assertFalse(run.condition_ready(condition))
            self.assertEqual([r.kind for r in dungeon_flow.handle(s,event_for(run,key))],[0xae,0xaf,0xba])
            self.assertTrue(run.condition_ready(condition));self.assertTrue(s.part_end_notified)

    def test_encode_failure_preserves_actor_gate_and_clock(self):
        run=run_stage(0,1);s=session(run,part_end_notified=False)
        before=(copy.deepcopy(run.defeated),run.next,run.ready_at,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=RuntimeError('controlled encoder failure')):
            with self.assertRaisesRegex(RuntimeError,'controlled encoder failure'):dungeon_flow.handle(s,event_for(run,15))
        self.assertEqual((run.defeated,run.next,run.ready_at,s.part_end_notified,s.dungeon_clock.total,s.dungeon_clock.started),before)
        self.assertTrue(actor(run,15)['active'])

    def test_mutated_source_owner_graph_hp_unit_phase_and_lease_reject(self):
        for change in ('source','point','template','active','team','ally','boss','no_drop','dynamic','graph','graph_content','script',
                       'hp','owner','unit','lease','generation','phase','participants','transaction','performers','uid'):
            with self.subTest(change=change):
                run=run_stage(0,1);s=session(run);npc=actor(run,15);e=event_for(run,15)
                if change=='source':npc['source_index']=6
                if change=='point':npc['start_point']=37
                if change=='template':npc['template']=9433
                if change in ('active','team','ally','boss','no_drop','dynamic'):
                    npc[change]={'active':False,'team':0,'ally':True,'boss':True,'no_drop':True,'dynamic':True}[change]
                if change=='graph':run.graph['source_sha256']='0'*64
                if change=='graph_content':run.graph['stages']['0']['parts']['1']['conditions'][0]['kind']=3
                if change=='script':run.catalog=copy.copy(run.catalog);run.catalog.manifest=copy.deepcopy(run.catalog.manifest);run.catalog.manifest['source_sha256']['LITHIA_MEMORY8_BUG.lua']='0'*64
                if change=='hp':e=Event(0x202,performers=(0,),kind=0xad,payload=native255(15,500))
                if change=='owner':e=event_for(run,15,owner=OWNER+1)
                if change=='unit':s.account.character=lambda:{'unit_type':16,'level':70}
                if change=='lease':s.application.playing[71]=object()
                if change=='generation':s.reward_run_id='other-run'
                if change=='phase':s.phase='town_ready'
                if change=='participants':s.dungeon_participants=frozenset((OWNER,OWNER+1))
                if change=='transaction':s.reward_transaction=object()
                if change=='performers':e=Event(0x202,performers=(1,),kind=0xad,payload=e.payload)
                if change=='uid':e=Event(0x202,performers=(0,),kind=0xad,payload=e.payload,uid=OWNER)
                result=dungeon_flow.handle(s,e)
                self.assertIn(result,([],None));self.assertFalse(run.defeated)

    def test_other_sources_and_35321_do_not_gain_combat_expiry(self):
        for dungeon,stage,part,key in ((35320,0,1,14),(35320,1,0,0),(35321,0,0,4)):
            run=run_stage(stage,part,dungeon);s=session(run)
            self.assertEqual(dungeon_flow.handle(s,event_for(run,key)),[])
            self.assertFalse(run.defeated)

    def test_conflicting_replay_rejects(self):
        run=run_stage(0,1);s=session(run);e=event_for(run,15)
        dungeon_flow.handle(s,e)
        changed=bytearray(e.payload);struct.pack_into('>f',changed,21,1)
        self.assertEqual(dungeon_flow.handle(s,Event(0x202,performers=(0,),kind=0xad,payload=bytes(changed))),[])
        self.assertEqual(run.defeated,{15:e.payload})

    def test_packet_shape_alone_cannot_authorize_a_combat_expiry(self):
        for change in ('source','killer','owner','status','last_uid','extra_uid'):
            run=run_stage(0,1);s=session(run);e=event_for(run,15)
            from els_server.domain.dungeon_lifecycle import death_report
            report=death_report(e.payload)
            if change=='owner':report['readiness']={OWNER+1:0}
            else:report[change]=OWNER if change in ('source','killer') else 7
            self.assertEqual(dungeon_flow.source_actor_expiry(s,e,report),[])
            self.assertFalse(run.defeated)

if __name__=='__main__':unittest.main()
