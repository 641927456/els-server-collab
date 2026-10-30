"""Devildom raid 2 (34140) only retires its own declared class103 markers."""
import struct
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import devildom1_raid2_controllers as devildom
from els_server.domain import dungeon_flow
from els_server.domain import dungeon_routes
from els_server.domain.dungeon_lifecycle import death_report
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event

OWNER=1002
MAX_UID=2**64-1
GRAPH_SHA='e19bb64e80a3788b985b54910c9ad4d29004f29234c68db933bdb395d83930a3'


class FakeClock:
    def __init__(self):self.value=0.0;self.total=0.0;self.started=None
    def __call__(self):return self.value
    def pause(self):self.started=None
    def resume(self):self.started=self.value


def native255(index,hp,owner=OWNER,xyz=(0.0,)*6):
    """Original 16E1760 source retirement: sentinel identity, one zero readiness."""
    return (struct.pack('>iBQQ6fBI',index,255,MAX_UID,MAX_UID,*xyz,1,
                        struct.unpack('>I',struct.pack('>f',float(hp)))[0])
            +struct.pack('>I',0)+struct.pack('>IQB',1,owner,0)+struct.pack('>Q',0)
            +struct.pack('>I',0)+struct.pack('>Q',0))


def fixture(stage=0,unit=15):
    clock=FakeClock()
    run=dungeon_routes.DungeonRun(34140,'00000000-0000-0000-0000-000000000341',clock=clock)
    if stage:run.stage=stage;run._load_stage(stage)
    run.loaded()
    session=NS(dungeon_run=run,account=NS(uid=OWNER,character=lambda:{'unit_type':unit}),
               role='game',phase='dungeon_active',dungeon_substage_synced=True,
               clear_notified=False,part_end_notified=False,dungeon_clock=clock,
               dungeon_participants=frozenset((OWNER,)),reward_run_id=run.run_id,
               reward_transaction=None,summon_keys=set(),defeated_npcs=run.defeated,
               challenge_deadline=None,application=None,drop_probe=False,
               world_drops={},world_drop_sequence=0,gate_stage_loading=False,
               gate_stage=0,previous_dungeon_part=None,summon_deaths={},
               summon_requests={},summon_next_key=16)
    return session,run,clock


def call(s,event):
    with patch.dict(sys.modules,{
            'els_server.domain.hunter_chest_flow':NS(accepted_death=lambda *a:None,
                                                     solo_loaded=lambda *a:[]),
            'els_server.domain.lithia_memory1_retirements':NS(handle=lambda *a:None),
            'els_server.domain.scene_actor_retirements':NS(handle=lambda *a:None),
            'els_server.domain.story_controller_retirements':NS(handle=lambda *a:None,
                                                                gate_predecessor_blocked=lambda *a:False),
            'els_server.domain.dungeon_equipment_loot_flow':NS(accepted_death=lambda *a:None,
                                                               current_lease=lambda *a:True),
            'els_server.domain.pve_economy_flow':NS(prepared_death=lambda *a:None),
            'els_server.domain.raid_economy_flow':NS(managed=lambda *a:False,solo=lambda *a:None),
            'els_server.domain.legacy_pve_exp':NS(accepted_death=lambda *a:None)}):
        return dungeon_flow.handle(s,event)


def retire(index,hp=30000.0,owner=OWNER,xyz=(0.0,)*6):
    return Event(0x202,performers=(0,),kind=0xad,payload=native255(index,hp,owner,xyz))


def kill(index,hp,owner=OWNER):
    """Original player-attributed death: flag 0 with the owner in every map."""
    return Event(0x202,performers=(0,),kind=0xad,payload=(
        struct.pack('>iBQQ6fBI',index,0,owner,owner,0,0,0,0,0,0,1,
                    struct.unpack('>I',struct.pack('>f',float(hp)))[0])
        +struct.pack('>I',0)+struct.pack('>IQB',1,owner,0)+struct.pack('>Q',0)
        +struct.pack('>I',0)+struct.pack('>Q',owner)))


class DevildomRaid2Controllers(unittest.TestCase):
    def test_every_required_condition_names_a_declared_marker(self):
        session,run,_=fixture(0)
        self.assertEqual(run.graph['source_sha256'],GRAPH_SHA)
        for stage,required in ((0,6851),(1,6853),(2,6855)):
            if stage:run.stage=stage;run._load_stage(stage)
            conditions=run.current['conditions']
            self.assertEqual([(c['kind'],tuple(c['required'])) for c in conditions],[(3,(required,))])
            markers=[n for n in run.current['npcs'] if n['template']==required]
            self.assertEqual(len(markers),1)
            self.assertIs(markers[0]['active'],False)
            self.assertIs(markers[0]['no_drop'],True)

    def test_all_nine_markers_are_pinned_and_inactive(self):
        session,run,_=fixture(0)
        seen=[]
        for stage in (0,1,2):
            if stage:run.stage=stage;run._load_stage(stage)
            for npc in run.current['npcs']:
                if (stage,npc['key']) not in devildom.CONTROLLERS:continue
                rule=devildom.source_rule(run,npc)
                self.assertIsNotNone(rule,(stage,npc['key']))
                template=devildom.CONTROLLERS[(stage,npc['key'])][0]
                self.assertEqual(rule['source']['template'],template)
                self.assertEqual(client_data().npc(template)['script'],devildom.SCRIPTS[template])
                self.assertIs(npc['active'],False)
                seen.append((stage,npc['key']))
        self.assertEqual(len(seen),9)

    def test_retirement_of_the_required_marker_ends_the_part(self):
        session,run,clock=fixture(0)
        self.assertEqual([r.kind for r in call(session,retire(5))],[0xae,0xaf])
        self.assertIn(5,run.defeated);self.assertFalse(session.part_end_notified)
        self.assertEqual([r.kind for r in call(session,retire(7))],[0xae,0xaf])
        self.assertFalse(session.part_end_notified)
        clock.value=5.0
        self.assertEqual([r.kind for r in dungeon_flow.periodic(session)],[0xba])
        self.assertTrue(session.part_end_notified)
        self.assertEqual(run.next['kind'],1);self.assertEqual(run.next['stage'],1)

    def test_retirement_is_idempotent_and_byte_exact(self):
        session,run,clock=fixture(0)
        event=retire(5)
        self.assertEqual([r.kind for r in call(session,event)],[0xae,0xaf])
        self.assertEqual([r.kind for r in call(session,event)],[0xae])
        self.assertEqual(run.defeated,{5:event.payload})
        self.assertEqual(call(session,retire(5,xyz=(1.0,1.0,1.0,1.0,1.0,1.0))),[])
        self.assertEqual(run.defeated,{5:event.payload})

    def test_active_boss_and_adds_are_never_native_retired(self):
        session,run,_=fixture(0)
        for key in (0,1,2,3,4):
            self.assertEqual(call(session,retire(key,hp=run.current['npcs'][key]['hp'])),[])
            self.assertEqual(run.defeated,{})
        self.assertFalse(session.part_end_notified)

    def test_undeclared_marker_of_a_neighbouring_raid_is_not_admitted(self):
        session,run,_=fixture(0)
        run.identity=34120
        self.assertEqual(call(session,retire(7)),[])
        self.assertEqual(run.defeated,{})

    def test_foreign_owner_or_participant_is_rejected(self):
        session,run,_=fixture(0)
        self.assertEqual(call(session,retire(7,owner=OWNER+1)),[])
        session.dungeon_participants=frozenset((OWNER,OWNER+1))
        self.assertEqual(call(session,retire(7)),[])
        self.assertEqual(run.defeated,{})

    def test_plain_kill_flag_is_left_to_the_generic_path(self):
        session,run,_=fixture(0)
        payload=bytearray(native255(7,30000.0))
        struct.pack_into('>B',payload,4,0)
        report=death_report(bytes(payload))
        self.assertIsNone(devildom.handle(session,Event(0x202,performers=(0,),
                                                        kind=0xad,payload=bytes(payload)),report))
        self.assertEqual(run.defeated,{})

    def test_retirement_is_not_committed_when_encoding_fails(self):
        session,run,_=fixture(0)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=RuntimeError('encode must fail first')) as encoded:
            with self.assertRaises(RuntimeError):call(session,retire(7))
            encoded.assert_called()
        self.assertEqual(run.defeated,{});self.assertIsNone(run.next)
        self.assertFalse(session.part_end_notified)

    def test_retirement_unsticks_the_first_part_end_to_end(self):
        session,run,clock=fixture(0)
        self.assertEqual([r.kind for r in call(session,retire(7))],[0xae,0xaf])
        clock.value=5.0
        self.assertEqual([r.kind for r in dungeon_flow.periodic(session)],[0xba])
        # The original portal gate still needs every active hostile of the part.
        gate=call(session,Event(0x202,performers=(0,),kind=0xb8,payload=b'\0'))
        self.assertEqual([r.kind for r in gate],[0xb9])
        self.assertEqual(struct.unpack('>i',gate[0].payload)[0],-1)
        for key in range(5):
            self.assertEqual([r.kind for r in call(session,kill(key,run.current['npcs'][key]['hp']))],[0xae,0xaf])
        gate=call(session,Event(0x202,performers=(0,),kind=0xb8,payload=b'\0'))
        self.assertEqual(struct.unpack('>i',gate[0].payload)[0],0)
        self.assertEqual([r.kind for r in call(session,Event(0x202,performers=(0,),kind=0xbb,payload=b'\0'))],[0xbc,0xb2])
        self.assertEqual((run.stage,run.part),(1,0))
        self.assertEqual(sorted(n['template'] for n in run.current['npcs']),[6831,6852,6853])

    def test_any_character_of_the_shared_raid_is_admitted(self):
        for unit in (1,5,10,15,17):
            session,run,_=fixture(0,unit=unit)
            self.assertEqual([r.kind for r in call(session,retire(7))],[0xae,0xaf],unit)
            self.assertIn(7,run.defeated)

    def test_stage_one_and_two_markers_end_their_own_parts(self):
        for stage,key in ((1,2),(2,2)):
            session,run,clock=fixture(stage)
            self.assertEqual([r.kind for r in call(session,retire(key))],[0xae,0xaf],stage)
            clock.value=5.0
            self.assertEqual([r.kind for r in dungeon_flow.periodic(session)],[0xba],stage)
            self.assertEqual(run.next['stage'],stage+1 if stage<2 else 0,stage)

    def test_stage_two_retirement_reaches_the_clear_entry(self):
        session,run,clock=fixture(2)
        self.assertEqual([r.kind for r in call(session,retire(2))],[0xae,0xaf])
        clock.value=5.0
        self.assertEqual([r.kind for r in dungeon_flow.periodic(session)],[0xba])
        self.assertEqual(run.next['kind'],4)
        cleared=[]
        def fake_clear(s):
            cleared.append((s.dungeon_run.stage,s.dungeon_run.part))
            return [Event(0x201,kind=0xc1,payload=bytes(4))]
        with patch.object(dungeon_flow,'clear',fake_clear):
            reply=call(session,Event(0x202,performers=(0,),kind=0xbb,payload=b'\0'))
        self.assertEqual([r.kind for r in reply],[0xbc,0xc1])
        self.assertEqual(cleared,[(2,0)])

    def test_raid_phase_settlement_shares_the_same_graph_pin(self):
        from els_server.domain import formal_raid_economy
        definition=formal_raid_economy.definition(34140)
        self.assertIsNotNone(definition)
        self.assertEqual(definition['graph_sha256'],devildom.GRAPH_SHA)
        self.assertEqual(definition['phases'],{'0':1,'1':2,'2':3})
        # Raid settlement rejects a phase whose cursor is still unset, so the
        # part-end cursor this module produces is that settlement's precondition.
        session,run,clock=fixture(0)
        self.assertIsNone(run.next)
        self.assertEqual([r.kind for r in call(session,retire(7))],[0xae,0xaf])
        self.assertEqual(run.ready_at,5.0)
        clock.value=5.0
        self.assertEqual([r.kind for r in dungeon_flow.periodic(session)],[0xba])
        self.assertIsInstance(run.next,dict)
        self.assertEqual(run.next['kind'],1)

    def test_toggle_only_disables_the_new_admission(self):
        session,run,_=fixture(0)
        with patch.object(devildom,'DEVILDOM1_RAID2_CONTROLLERS_ENABLED',False):
            self.assertEqual(devildom.handle(session,retire(7),{
                'flag':255,'index':7,'hp_bits':struct.unpack('>I',struct.pack('>f',30000.0))[0],
                'status':1,'source':MAX_UID,'killer':MAX_UID,'last_uid':0,'extra_uid':0,
                'contribution':{},'counters':{},'readiness':{OWNER:0},'xyz':(0.0,)*6}),None)


if __name__=='__main__':unittest.main()
