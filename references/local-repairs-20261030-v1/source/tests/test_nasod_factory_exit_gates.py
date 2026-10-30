"""纳斯德生产基地 (30282) must progress past its 小boss exit gates.

Regression: stage 0 part 1 and stage 1 part 1 both exit through a kind-1
condition whose ``required`` key_code 1 belongs to template 156
(``SMALLGATE_BESMA_AIR_SHIP``), declared ``active=false / no_drop=true /
team=1``. The map script removes that door itself when the room is done, so
the server never receives a combat death for it and the exit condition waited
forever - the player killed the mid-boss (stage 1, template 193) and the
portal never opened. The kind-3 template-door relaxation (dragon nest) already
exists; this extends the same treatment to key_code doors.
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


def death_event(key, owner=1004, flag=0):
    payload = (struct.pack('>iBQQ6fBI', key, flag, owner, owner,
                           1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1,
                           struct.unpack('>I', struct.pack('>f', 100.0))[0])
               + struct.pack('>I', 0) + struct.pack('>IQB', 1, owner, 0)
               + struct.pack('>Q', 0) + struct.pack('>I', 0) + struct.pack('>Q', owner))
    return Event(0x202, performers=(0,), kind=0xad, payload=payload)


from els_server.protocol.protocol_codec import Event  # noqa: E402


class NasodFactoryRun(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.run = dungeon_routes.DungeonRun(30282, str(uuid.uuid4()), clock=self.clock)
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
        self.acked = []

    def kill(self, npc):
        # The production writer needs a durable store; the death itself is what
        # this regression exercises, so record the defeat the way finish_death
        # does and keep only the acknowledgement.
        self.run.defeated[npc['key']] = bytes(death_event(npc['key']).payload)
        self.session.defeated_npcs = self.run.defeated

    def kill_room(self):
        for npc in list(self.run.current['npcs']):
            if npc['active'] and npc.get('team', 1) != 0 and not npc.get('ally'):
                self.kill(npc)

    def walk(self):
        """Drive the whole map; return the part transitions in order."""
        steps = []
        for stage in range(3):
            self.run._load_stage(stage)
            for part in sorted(self.run.parts):
                self.run.part = part
                self.kill_room()
                self.run.started_at = 0.0
                self.assertTrue(self.run.poll_ready(),
                                f'stage {stage} part {part} exit never opened')
                steps.append(self.run.advance())
        return steps

    def test_the_exit_conditions_name_the_smallgate_door(self):
        graph = self.run.catalog.graph(30282)
        for stage, part in (('0', '1'), ('1', '1')):
            condition = graph['stages'][stage]['parts'][part]['conditions'][0]
            self.assertEqual(condition['kind'], 1)
            self.assertEqual(condition['required'], [1])
            doors = [n for n in graph['stages'][stage]['parts'][part]['groups'][0]['npcs']
                     if n.get('key_code') == 1]
            self.assertEqual([n['template'] for n in doors], [156])
            self.assertFalse(doors[0]['active'])
            self.assertTrue(local_dungeon_flow.script_door(dict(doors[0], key=0)))

    def test_full_run_reaches_the_clear_after_the_mid_boss(self):
        transitions = self.walk()
        self.assertEqual(transitions, ['part', 'stage', 'part', 'stage', 'clear'])

    def test_mid_boss_room_declares_the_expected_actors(self):
        self.run._load_stage(1)
        self.run.part = 1
        templates = [n['template'] for n in self.run.current['npcs']]
        self.assertIn(193, templates)   # 小boss
        self.assertIn(156, templates)   # SMALLGATE 出口门
        self.assertIn(157, templates)   # SMALLGATE 后门

    def test_mid_boss_room_exits_without_the_door_death(self):
        self.run._load_stage(1)
        self.run.part = 1
        self.kill_room()
        self.run.started_at = 0.0
        self.assertTrue(self.run.poll_ready())
        self.assertEqual(self.run.advance(), 'stage')
        self.assertEqual((self.run.stage, self.run.part), (2, 0))

    def test_living_required_actor_is_never_relaxed(self):
        # A key_code condition that names a real combat actor must stay on the
        # strict all-dead path: the door relaxation refuses and condition_ready
        # keeps its original check. (The 30282-shaped rows are the only ones
        # waived here; 厄泰拉核心 stage 2 is waived by its own pinned source
        # row, not by this shape check.)
        npcs = [dict(key=1, template=7, key_code=1, active=True, boss=False,
                     no_drop=False, ally=False, team=1),
                dict(key=2, template=8, key_code=-1, active=True, boss=False,
                     no_drop=False, ally=False, team=1)]
        self.assertFalse(local_dungeon_flow.key_code_gate(npcs, {2}, [1]))
        self.assertFalse(local_dungeon_flow.key_code_gate(npcs, {1, 2}, [1]))
        self.assertTrue(local_dungeon_flow.script_gate(
            [dict(n, key=n['key']) for n in npcs], {1, 2}, [7]) is False)

    def test_relaxation_switch_still_gates_the_new_path(self):
        npcs = [dict(key=1, template=156, key_code=1, active=False, boss=False,
                     no_drop=True, ally=False, team=1),
                dict(key=2, template=9, key_code=-1, active=True, boss=False,
                     no_drop=False, ally=False, team=1)]
        with patch.object(local_dungeon_flow, 'script_gate_relaxation', lambda: False):
            self.assertFalse(local_dungeon_flow.key_code_gate(npcs, {2}, [1]))
        self.assertTrue(local_dungeon_flow.key_code_gate(npcs, {2}, [1]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
