"""Actors that leave the field retire through the native 255 report, clearing only.

Server log 20261025-193058, run 2b9c8bdd-...: the player was in 35320
(LITHIA_MEMORY8, 「学会研究设施」) stage0 part1, the room with the wooden
platform. Nine source-declared active hostiles guard the part's only kind-0
condition. Two of the four LITHIA_MEMORY8_BUG actors - wire key 15 (source_index
4, declared point 12) and wire key 17 (source_index 6, point 37) - were knocked
off the platform: their y fell to 0 while HP stayed at 500, HP reached 0 a second
later and the client destroyed both actors and reported each with the killerless
160-byte native expiry (requests 475 at 11:33:03.361Z and 481 at 11:33:04.267Z).
Nothing answered either report, so neither key entered run.defeated, the gate
never became ready, no part-end notice was emitted for part1 and the single
portal request at 11:37:26.442 was refused. The corpses stayed in the client's
actor list until the run was abandoned at 11:37:46 with no clear and quest 28550
still at 0.

The same refusal stranded 35320 stage1 part0 a few hours earlier (session
20261025-165751, request 5511: the fifth LITHIA_MEMORY8_PLANT_DROSERA expired
once the player killed the other four) and, before that, LITHIA_MEMORY2_FLOWER.
None of them is class 103 and no declaration names which actor leaves the
field, so admission cannot be an enumerated allow-list; it is the packet shape
that has to be strict. Retiring here grants nothing - the actor goes out of the
part's condition and nothing else.
"""
import struct
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import dungeon_flow
from els_server.domain import legacy_pve_exp
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.story_controller_retirements import source_pinned
from els_server.protocol.protocol_codec import Event

OWNER = 1001
MAX_UID = 2**64 - 1
DUNGEON = 35320
BUG = 9436
PLANT = 9433
CONTROLLER = 9450
# stage0 part1: the two bugs that fell off the platform.
FALL = {15: (4, [12]), 17: (6, [37])}
# stage1 part0: the Drosera the client expired without a killer.
PLANT_KEY, PLANT_SOURCE = 4, 5


def native255(key, hp, owner=OWNER, source=MAX_UID, killer=MAX_UID):
    return (struct.pack('>iBQQ6fBI', key, 255, source, killer, 0, 0, 0, 0, 0, 0, 1,
                        struct.unpack('>I', struct.pack('>f', float(hp)))[0])
            + struct.pack('>I', 0) + struct.pack('>IQB', 1, owner, 0) + struct.pack('>Q', 0)
            + struct.pack('>I', 0) + struct.pack('>Q', 0))


def run_stage(stage, part, dungeon=DUNGEON):
    run = DungeonRun(dungeon, '00000000-0000-4000-8000-000000000001')
    run._load_stage(stage)
    run.part = part
    run.loaded()
    return run


def session(run, *, part_end_notified=True):
    return NS(dungeon_run=run, account=NS(uid=OWNER, character=lambda: {'unit_type': 15, 'level': 70}),
              role='game', phase='dungeon_active', dungeon_substage_synced=True,
              clear_notified=False, part_end_notified=part_end_notified,
              dungeon_participants=frozenset((OWNER,)), reward_run_id=run.run_id, reward_transaction=None,
              reward_test=False, item_test=False, drop_probe=False, summon_keys=set(),
              defeated_npcs=run.defeated, world_drops={}, world_drop_sequence=0,
              dungeon_clock=NS(pause=lambda: None))


def actor(run, key):
    return next(n for n in run.current['npcs'] if n['key'] == key)


def gate(run):
    """The keys a kind-0 condition waits on: every active hostile in the part."""
    return {n['key'] for n in run.current['npcs'] if n['active'] and n.get('team', 1) != 0}


class FallenBugExpiry(unittest.TestCase):
    def test_the_observed_room_declares_both_fallen_bugs_as_plain_hostiles(self):
        run = run_stage(0, 1)
        self.assertEqual(gate(run), set(range(12, 21)))
        for key, (source, points) in FALL.items():
            with self.subTest(key=key):
                actor_ = actor(run, key)
                self.assertEqual((actor_['template'], actor_['source_index'], actor_['points'],
                                  actor_['hp'], actor_['active']), (BUG, source, points, 500, True))
                self.assertFalse(source_pinned(run, actor_))

    def test_the_observed_reports_retire_both_bugs_without_a_reward(self):
        run = run_stage(0, 1)
        s = session(run)
        for key in FALL:
            with self.subTest(key=key):
                reply = dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad,
                                                     payload=native255(key, 500)))
                self.assertEqual([e.kind for e in reply], [0xae, 0xaf])
                self.assertIn(key, run.defeated)
                self.assertFalse(actor(run, key)['active'])
        self.assertEqual(set(run.defeated), set(FALL))
        self.assertFalse(s.clear_notified)
        self.assertIsNone(s.reward_transaction)
        self.assertIsNone(getattr(s, 'world_drop_issued', None))

    def test_the_part_gate_opens_once_the_last_fallen_bug_retires(self):
        run = run_stage(0, 1)
        condition = run.current['conditions'][0]
        run.defeated = {k: b'hostile' for k in gate(run) - set(FALL)}
        s = session(run, part_end_notified=False)
        self.assertFalse(run.condition_ready(condition))
        first = dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad,
                                             payload=native255(min(FALL), 500)))
        self.assertEqual([e.kind for e in first], [0xae, 0xaf])
        self.assertFalse(run.condition_ready(condition))
        second = dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad,
                                              payload=native255(max(FALL), 500)))
        self.assertEqual([e.kind for e in second], [0xae, 0xaf, 0xba])
        self.assertTrue(run.condition_ready(condition))
        self.assertEqual((run.next['kind'], run.next['stage'], run.next['part']), (0, 0, 2))
        self.assertTrue(s.part_end_notified)

    def test_an_expired_actor_earns_no_kill_experience(self):
        run = run_stage(0, 1)
        actor_ = dict(actor(run, min(FALL)))
        self.assertTrue(legacy_pve_exp.eligible(actor_, expired=False))
        self.assertFalse(legacy_pve_exp.eligible(actor_, expired=True))


class PlantExpiry(unittest.TestCase):
    """35320 stage1 part0: the fifth Drosera expires once the other four die."""

    def test_the_observed_report_retires_the_plant_without_a_reward(self):
        run = run_stage(1, 0)
        s = session(run)
        plant = actor(run, PLANT_KEY)
        self.assertEqual((plant['template'], plant['source_index'], plant['points'], plant['hp']),
                         (PLANT, PLANT_SOURCE, [26], 500))
        reply = dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad,
                                             payload=native255(PLANT_KEY, 500)))
        self.assertEqual([e.kind for e in reply], [0xae, 0xaf])
        self.assertEqual(set(run.defeated), {PLANT_KEY})
        self.assertFalse(actor(run, PLANT_KEY)['active'])
        self.assertFalse(s.clear_notified)
        self.assertIsNone(getattr(s, 'world_drop_issued', None))

    def test_the_part_gate_opens_once_the_plant_retires(self):
        run = run_stage(1, 0)
        condition = run.current['conditions'][0]
        self.assertIn(PLANT_KEY, gate(run))
        run.defeated = {k: b'hostile' for k in gate(run) - {PLANT_KEY}}
        s = session(run, part_end_notified=False)
        self.assertFalse(run.condition_ready(condition))
        reply = dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad,
                                             payload=native255(PLANT_KEY, 500)))
        self.assertEqual([e.kind for e in reply], [0xae, 0xaf, 0xba])
        self.assertTrue(run.condition_ready(condition))
        self.assertEqual((run.next['kind'], run.next['stage'], run.next['part']), (1, 2, 0))


class ExpiryPacketBoundaries(unittest.TestCase):
    """Widening admission to every declared actor leaves the packet shape as the guard."""

    def test_a_report_naming_a_killer_is_not_an_expiry(self):
        run = run_stage(0, 1)
        s = session(run)
        self.assertEqual(dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad,
                                                      payload=native255(15, 500, source=OWNER))), [])
        self.assertFalse(run.defeated)

    def test_a_foreign_readiness_owner_is_refused(self):
        run = run_stage(0, 1)
        s = session(run)
        self.assertEqual(dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad,
                                                      payload=native255(15, 500, owner=OWNER + 1))), [])
        self.assertFalse(run.defeated)

    def test_a_creditied_player_kill_stays_a_kill(self):
        # A credited kill names the killer, carries a contribution and earns the
        # hostile's reward path; only the killerless expiry retires silently.
        run = run_stage(1, 0)
        s = session(run)
        plant = actor(run, PLANT_KEY)
        payload = (struct.pack('>iBQQ6fBI', plant['key'], 1, OWNER, OWNER, 0, 0, 0, 0, 0, 0, 1,
                               struct.unpack('>I', struct.pack('>f', float(plant['hp'])))[0])
                   + struct.pack('>I', 1) + struct.pack('>Qf', OWNER, 500.0)
                   + struct.pack('>I', 1) + struct.pack('>QB', OWNER, 0)
                   + struct.pack('>Q', 0)
                   + struct.pack('>I', 1) + struct.pack('>Qi', OWNER, 1)
                   + struct.pack('>Q', OWNER))
        reply = dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad, payload=payload))
        self.assertEqual([e.kind for e in reply], [0xae, 0xaf])
        self.assertIn(plant['key'], run.defeated)
        self.assertTrue(actor(run, PLANT_KEY)['active'])

    def test_a_source_pinned_actor_is_not_consumed_by_the_generic_path(self):
        # 9450 at stage1 part0 source_index 10 is a pinned retirement rule with
        # quest 28550 on it. Its own rule answers the report; the generic branch
        # must not retire it, or a killerless packet would clear the objective.
        run = run_stage(1, 0)
        controller = actor(run, 9)
        self.assertEqual((controller['template'], controller['source_index']), (CONTROLLER, 10))
        self.assertTrue(source_pinned(run, controller))
        s = session(run)
        with patch('els_server.domain.story_controller_retirements.handle', return_value=None):
            self.assertEqual(dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad,
                                                          payload=native255(9, 1000))), [])
        self.assertFalse(run.defeated)


if __name__ == '__main__':
    unittest.main()
