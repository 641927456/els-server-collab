"""Class103 metadata alone never authorizes an unqualified static expiry."""
import struct
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import dungeon_flow
from els_server.domain import story_controller_retirements as story
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event

OWNER=1001
MAX_UID=2**64-1


def native255(key,hp,owner=OWNER):
    return (struct.pack('>iBQQ6fBI',key,255,MAX_UID,MAX_UID,0,0,0,0,0,0,1,
                        struct.unpack('>I',struct.pack('>f',float(hp)))[0])
            +struct.pack('>I',0)+struct.pack('>IQB',1,owner,0)+struct.pack('>Q',0)
            +struct.pack('>I',0)+struct.pack('>Q',0))


def npc(key,template,hp,active=True):
    return {'key':key,'template':template,'active':active,'team':1,'no_drop':False,
            'ally':False,'dynamic':False,'source_index':key+1,'hp':hp,'boss':False}


def fixture(actor):
    run=NS(identity=35260,run_id='scene-expiry',stage=0,part=1,
           current={'npcs':[actor]},defeated={},next=None,ready_at=None)
    session=NS(dungeon_run=run,account=NS(uid=OWNER),role='game',phase='dungeon_active',
               dungeon_substage_synced=True,clear_notified=False,part_end_notified=True,
               dungeon_participants=frozenset((OWNER,)),reward_run_id=run.run_id,reward_transaction=None,
               summon_keys=set(),defeated_npcs=run.defeated,drop_probe=False,
               world_drops={},world_drop_sequence=0)
    return session,run


def call(s,e):
    with ExitStack()as stack:
        stack.enter_context(patch.dict(sys.modules,{
            'els_server.domain.hunter_chest_flow':NS(accepted_death=lambda *a:None),
            'els_server.domain.lithia_memory1_retirements':NS(handle=lambda *a:None),
            'els_server.domain.story_controller_retirements':NS(
                handle=lambda *a:None,source_pinned=lambda run,npc:npc.get('template')==9324),
            'els_server.domain.dungeon_equipment_loot_flow':NS(accepted_death=lambda *a:None,
                                                               current_lease=lambda *a:True),
            'els_server.domain.legacy_pve_exp':NS(accepted_death=lambda *a:None)}))
        return dungeon_flow.handle(s,e)


class SceneActorNativeExpiry(unittest.TestCase):
    def test_active_class103_flower_without_qualified_source_rejects(self):
        self.assertEqual(client_data().npc(9323)['class_id'],103)
        actor=npc(12,9323,5000,active=True)
        s,run=fixture(actor)
        reply=call(s,Event(0x202,performers=(0,),kind=0xad,payload=native255(12,5000)))
        self.assertEqual(reply,[])
        self.assertFalse(run.defeated)
        self.assertTrue(actor['active'])
        self.assertFalse(s.clear_notified)

    def test_inactive_class103_controller_without_qualified_source_rejects(self):
        self.assertEqual(client_data().npc(9320)['class_id'],103)
        actor=npc(0,9320,1000,active=False)
        s,run=fixture(actor)
        reply=call(s,Event(0x202,performers=(0,),kind=0xad,payload=native255(0,1000)))
        self.assertEqual(reply,[])
        self.assertFalse(run.defeated)

    def test_combat_actor_still_rejects_native_expiry(self):
        self.assertEqual(client_data().npc(9312)['class_id'],0)
        actor=npc(0,9312,800,active=True)
        s,run=fixture(actor)
        self.assertEqual(call(s,Event(0x202,performers=(0,),kind=0xad,payload=native255(0,800))),[])
        self.assertFalse(run.defeated)

    def test_source_pinned_controller_is_not_consumed_by_generic_path(self):
        actor=npc(18,9324,1000,active=True)
        s,run=fixture(actor)
        self.assertEqual(call(s,Event(0x202,performers=(0,),kind=0xad,payload=native255(18,1000))),[])
        self.assertFalse(run.defeated)

    def test_route_declares_9324_but_not_the_flowers(self):
        run=NS(identity=35260,stage=0,part=1)
        self.assertTrue(story.source_pinned(run,{'template':9324,'source_index':7}))
        self.assertFalse(story.source_pinned(run,{'template':9323,'source_index':1}))

    def test_foreign_readiness_owner_is_still_rejected(self):
        actor=npc(12,9323,5000,active=True)
        s,run=fixture(actor)
        payload=native255(12,5000,owner=OWNER+1)
        self.assertEqual(call(s,Event(0x202,performers=(0,),kind=0xad,payload=payload)),[])
        self.assertFalse(run.defeated)

    def test_unqualified_scene_does_not_mutate_before_encoding(self):
        actor=npc(12,9323,5000,active=True);before=dict(actor)
        s,run=fixture(actor)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=RuntimeError('must not encode rejected scene')) as encoded:
            self.assertEqual(call(s,Event(0x202,performers=(0,),kind=0xad,payload=native255(12,5000))),[])
            encoded.assert_not_called()
        self.assertEqual(actor,before);self.assertFalse(run.defeated)
        self.assertIsNone(run.next);self.assertIsNone(run.ready_at)
        self.assertFalse(s.clear_notified);self.assertFalse(s.world_drops)

    def test_original_server_allocated_dynamic_expiry_is_preserved(self):
        actor=npc(12,9323,5000,active=True);actor['dynamic']=True
        s,run=fixture(actor)
        e=Event(0x202,performers=(0,),kind=0xad,payload=native255(12,5000))
        self.assertEqual([r.kind for r in call(s,e)],[0xae,0xaf])
        self.assertEqual([r.kind for r in call(s,e)],[0xae])
        self.assertEqual(run.defeated,{12:e.payload});self.assertFalse(actor['active'])


if __name__=='__main__':unittest.main()
