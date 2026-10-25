"""Every source-declared actor retires through the generic AD path, active or not.

LITHIA_MEMORY2_FLOWER is source-declared ISACTIVE but the client retires it
with the native 255 report. Rejecting that report left the flowers' actors
alive and the part gate (9324) never opened.
"""
import struct
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import dungeon_flow
from els_server.domain import story_controller_retirements as story
from els_server.domain.dungeon_spawns import scene_controller
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
    run=NS(identity=35260,run_id='scene-expiry',stage=0,part=1,graph={'source_sha256':''},
           current={'npcs':[actor]},defeated={},retreated=set(),next=None,ready_at=None)
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
    def test_active_class103_flower_retires_without_rewards(self):
        self.assertTrue(scene_controller(9323))
        actor=npc(12,9323,5000,active=True)
        s,run=fixture(actor)
        reply=call(s,Event(0x202,performers=(0,),kind=0xad,payload=native255(12,5000)))
        self.assertEqual([e.kind for e in reply],[0xae,0xaf])
        self.assertEqual(set(run.defeated),{12})
        self.assertFalse(actor['active'])
        self.assertFalse(s.clear_notified)

    def test_inactive_scene_controller_keeps_retiring(self):
        actor=npc(0,9320,1000,active=False)
        s,run=fixture(actor)
        reply=call(s,Event(0x202,performers=(0,),kind=0xad,payload=native255(0,1000)))
        self.assertEqual([e.kind for e in reply],[0xae,0xaf])
        self.assertEqual(set(run.defeated),{0})

    def test_combat_actor_also_retires_on_a_valid_native_expiry(self):
        # Admission is the packet shape, not the actor class: 35320's Drosera and
        # platform bugs are class 0 and strand their rooms when refused.
        self.assertFalse(scene_controller(9312))
        actor=npc(0,9312,800,active=True)
        s,run=fixture(actor)
        reply=call(s,Event(0x202,performers=(0,),kind=0xad,payload=native255(0,800)))
        self.assertEqual([e.kind for e in reply],[0xae,0xaf])
        self.assertEqual(set(run.defeated),{0})
        self.assertFalse(actor['active'])
        self.assertFalse(s.clear_notified)

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


if __name__=='__main__':unittest.main()
