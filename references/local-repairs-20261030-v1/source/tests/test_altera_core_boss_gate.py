"""厄泰拉核心 (30302) must reach its boss map.

Regression: stage 2 part 0 is the single room guarding stage 3 (纳斯德之王动力
装置). Its only exit condition is ``{"kind": 1, "required": [1]}`` - every
actor whose key_code is 1 has to die - and the room declares exactly one actor,
template 343 (``NUI_PD_MONSTER``, key 0, 9225 hp). That row is combat-shaped
(``active=true``, ``no_drop=false``) but its native record is ``class_id 103``
with ``IS_NPC`` true: the scene-object family the Lithia Memory2 flowers
(template 9323) belong to. Those flowers proved that such an actor leaves the
scene through a native flag-255 retirement, which the generic combat path drops
before it can reach ``run.defeated``. The server therefore never satisfied the
exit condition and answered the client's 0xb8 portal request with ``result=-1``,
so the boss gate never opened.

The census over all pinned graphs puts key_code exit conditions on class-100
doors 10 times (already relaxed by ``script_gate_relaxation``), on class-0
monsters 33 times and on class 103 exactly once: this actor. Template 343
appears nowhere else in the graph set.
"""
import struct
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from els_server.domain import dungeon_flow, dungeon_routes, local_dungeon_flow
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event

BOSS_STAGE = 3


class FakeClock:
    def __init__(self):
        self.value = 100.0
        self.total = 0.0
        self.started = 0.0

    def __call__(self):
        return self.value

    def pause(self):
        self.started = None

    def resume(self):
        self.started = self.value

    def seconds(self):
        return 5


def portal_request(part):
    return Event(0x202, kind=0xb8, payload=struct.pack('>b', part))


class AlteraCoreBossGate(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.run = dungeon_routes.DungeonRun(30302, str(uuid.uuid4()), clock=self.clock)
        self.session = NS(dungeon_run=self.run,
                          account=NS(uid=1004, character=lambda: {'unit_type': 15}),
                          role='game', phase='dungeon_active', dungeon_substage_synced=True,
                          clear_notified=False, dungeon_failed=False, part_end_notified=False,
                          dungeon_clock=self.clock, dungeon_participants=frozenset((1004,)),
                          reward_run_id=self.run.run_id, reward_transaction=None,
                          challenge_deadline=None, drop_probe=False, world_drops={},
                          world_drop_sequence=0, gate_stage_loading=False, gate_stage=0,
                          previous_dungeon_part=None, summon_keys=set(), summon_deaths={},
                          summon_requests={}, summon_next_key=16,
                          defeated_npcs=self.run.defeated, application=None,
                          active_challenge=None, clear_items_synced=False)

    def kill(self, npc):
        self.run.defeated[npc['key']] = b'\0'
        self.session.defeated_npcs = self.run.defeated

    def kill_room(self):
        for npc in list(self.run.current['npcs']):
            if npc['active'] and npc.get('team', 1) != 0:
                self.kill(npc)

    def gate_actor(self):
        self.run._load_stage(2)
        self.run.part = 0
        return self.run.current['npcs']

    def enter_gate(self):
        """Stand in the boss-gate room with its (empty) hostile roster cleared."""
        self.run._load_stage(2)
        self.run.part = 0
        self.run.started_at = 0.0
        self.session.defeated_npcs = self.run.defeated

    def walk(self):
        steps = []
        for stage in (0, 1, 2, BOSS_STAGE):
            self.run._load_stage(stage)
            for part in sorted(self.run.parts):
                self.run.part = part
                self.kill_room()
                self.run.started_at = 0.0
                self.assertTrue(self.run.poll_ready(),
                                f'stage {stage} part {part} exit never opened')
                steps.append(self.run.advance())
        return steps

    def test_the_gate_is_the_boss_stages_only_room(self):
        graph = self.run.catalog.graph(30302)
        condition = graph['stages']['2']['parts']['0']['conditions'][0]
        self.assertEqual((condition['kind'], condition['required']), (1, [1]))
        self.assertEqual(condition['next'][0]['stage'], BOSS_STAGE)
        npcs = self.gate_actor()
        self.assertEqual([n['template'] for n in npcs], [343])
        self.assertEqual([n['key_code'] for n in npcs], [1])

    def test_the_required_actor_is_a_scene_object_not_a_combat_actor(self):
        native = client_data().npc(343)
        self.assertEqual(native['class_id'], 103)
        self.assertIs(native['is_npc'], True)
        self.assertEqual(native['script'], 'PD_Monster.lua')

    def test_the_pinned_row_admits_only_that_source(self):
        npc = self.gate_actor()[0]
        self.assertTrue(local_dungeon_flow.scene_object_npc(self.run, npc))
        # Another part of the same map is not admitted, even for the same row.
        self.run._load_stage(BOSS_STAGE)
        self.run.part = 0
        boss = next(n for n in self.run.current['npcs'] if n['key_code'] == 1)
        self.assertEqual(boss['template'], 338)
        self.assertFalse(local_dungeon_flow.scene_object_npc(self.run, boss))

    def test_full_run_reaches_the_boss_map_and_the_clear(self):
        self.assertEqual(self.walk(),
                         ['stage', 'part', 'part', 'stage', 'stage', 'clear'])

    def test_gate_room_opens_without_a_death_report_for_343(self):
        self.enter_gate()
        self.assertEqual(self.run.defeated, {})
        self.assertTrue(self.run.poll_ready())
        self.assertEqual(self.run.advance(), 'stage')
        self.assertEqual((self.run.stage, self.run.part), (BOSS_STAGE, 0))

    def test_portal_request_is_acknowledged_and_notices_the_end(self):
        self.enter_gate()
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(reply[0].kind, 0xb9)
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)
        self.assertTrue(self.session.part_end_notified)
        self.assertTrue(self.run.poll_ready())

    def test_transition_request_loads_the_boss_stage(self):
        self.enter_gate()
        dungeon_flow.handle(self.session, portal_request(0))
        reply = dungeon_flow.handle(
            self.session, Event(0x202, kind=0xbb, payload=struct.pack('>b', 0)))
        self.assertEqual([event.kind for event in reply][:2], [0xbc, 0xb2])
        self.assertEqual((self.run.stage, self.run.part), (BOSS_STAGE, 0))
        self.assertTrue(self.session.gate_stage_loading)
        self.assertFalse(self.session.dungeon_substage_synced)
        self.assertEqual(struct.unpack('>i', reply[1].payload[:4])[0], BOSS_STAGE)
        self.assertIn(338, [n['template'] for n in self.run.current['npcs']])

    def test_boss_room_still_requires_the_real_boss(self):
        self.run._load_stage(BOSS_STAGE)
        self.run.part = 0
        self.run.started_at = 0.0
        self.assertFalse(self.run.poll_ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], -1)
        for npc in self.run.current['npcs']:
            if npc['active'] and npc.get('team', 1) != 0:
                self.kill(npc)
        self.assertTrue(self.run.poll_ready())

    def test_a_living_hostile_alongside_the_object_still_blocks_the_gate(self):
        self.enter_gate()
        matched = [n for n in self.run.current['npcs'] if n['key_code'] == 1]
        alien = dict(self.run.current['npcs'][0], key=99, template=200, key_code=-1)
        self.assertFalse(local_dungeon_flow.scene_object_gate(
            self.run, self.run.current['npcs'] + [alien], set(), matched))
        self.assertTrue(local_dungeon_flow.scene_object_gate(
            self.run, self.run.current['npcs'] + [alien], {99}, matched))

    def test_switch_off_restores_the_upstream_refusal(self):
        self.enter_gate()
        with patch.object(local_dungeon_flow, 'scene_object_exit', lambda: False):
            self.assertFalse(self.run.poll_ready())
            reply = dungeon_flow.handle(self.session, portal_request(0))
            self.assertEqual(struct.unpack('>i', reply[0].payload)[0], -1)
            self.assertFalse(self.session.part_end_notified)


if __name__ == '__main__':
    unittest.main(verbosity=2)
