"""A client part-end request must survive the boss death-report race.

34720 session 20261031-095159: the boss room's add deaths arrived at
10:00:26, the client sent BB at 10:00:32.460 (its own room count was zero),
the boss death report 0xad landed at 10:00:33.375, and the room's source
condition carries a 5 s delay. The server dropped the BB (``part_end_notified``
was still false), announced the part end one second later, and the client --
already waiting for its BC -- never sent another BB. The run sat in the last
room for eight minutes.

The hold below keeps the client's request for the current part and answers it
on the tick the source condition matures. No actor, death, or clear is
invented: a living boss still blocks it.
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
from els_server.protocol.protocol_codec import Event

SIGHT, PORTRAIT = 34710, 34720


class FakeClock:
    def __init__(self):
        self.value = 100.0
        self.started = 0.0

    def __call__(self):
        return self.value

    def pause(self):
        self.started = None

    def resume(self):
        self.started = self.value

    def seconds(self):
        return 5


def part_end_request(part):
    return Event(0x202, performers=(0,), kind=0xbb, payload=struct.pack('>b', part))


class PartEndHold(unittest.TestCase):
    def enter(self, identity, stage, part=0):
        self.clock = FakeClock()
        self.run = dungeon_routes.DungeonRun(identity, str(uuid.uuid4()), clock=self.clock)
        self.run._load_stage(stage)
        self.run.part = part
        self.run.started_at = 0.0
        self.session = NS(dungeon_run=self.run,
                          account=NS(uid=1004, character=lambda: {'unit_type': 15}),
                          role='game', phase='dungeon_active', dungeon_substage_synced=True,
                          clear_notified=False, dungeon_failed=False, part_end_notified=False,
                          dungeon_clock=self.clock, dungeon_participants=frozenset((1004,)),
                          reward_run_id=self.run.run_id, reward_transaction=None,
                          challenge_deadline=None, drop_probe=False, world_drops={},
                          world_drop_sequence=0, gate_stage_loading=False, gate_stage=0,
                          previous_dungeon_part=None, summon_keys=set(), summon_deaths={},
                          summon_requests={}, summon_next_key=16, pending_part_end=None,
                          defeated_npcs=self.run.defeated, application=None,
                          active_challenge=None, clear_items_synced=False)
        return self.run

    def boss_keys(self, *templates):
        return [n['key'] for n in self.run.current['npcs'] if n['template'] in templates]

    def test_cursor_is_unchanged_while_the_request_is_held(self):
        run = self.enter(SIGHT, 7)
        self.assertEqual(dungeon_flow.handle(self.session, part_end_request(0)), [])
        self.assertEqual((run.stage, run.part), (7, 0))
        self.assertEqual(self.session.pending_part_end, 0)
        # A retry of the same standing request is idempotent.
        self.assertEqual(dungeon_flow.handle(self.session, part_end_request(0)), [])
        self.assertEqual((run.stage, run.part), (7, 0))

    def test_a_living_boss_still_blocks_the_held_request(self):
        run = self.enter(SIGHT, 7)
        first, second = self.boss_keys(8155, 8156)
        run.defeated[first] = b'\0'
        self.assertEqual(dungeon_flow.handle(self.session, part_end_request(0)), [])
        self.assertEqual(dungeon_flow.periodic(self.session), [])
        self.clock.value += 10
        self.assertEqual(dungeon_flow.periodic(self.session), [])
        self.assertEqual((run.stage, run.part), (7, 0))
        self.assertFalse(self.session.clear_notified)
        # The second boss still has to die before anything settles.
        self.assertIn(second, [n['key'] for n in run.current['npcs'] if n['template'] == 8156])

    def test_held_request_settles_the_final_room_once_the_delay_elapses(self):
        run = self.enter(SIGHT, 7)
        for key in self.boss_keys(8155, 8156):
            run.defeated[key] = b'\0'
        self.assertEqual(dungeon_flow.handle(self.session, part_end_request(0)), [])
        # First poll arms the room's native 5 s delay without settling.
        self.assertEqual(dungeon_flow.periodic(self.session), [])
        self.clock.value += 6
        cleared = []

        def settle(s):
            cleared.append((s.dungeon_run.stage, s.dungeon_run.part))
            s.clear_notified = True
            return [Event(0x201, kind=0xc1, payload=bytes(4))]

        with patch.object(dungeon_flow, 'clear', settle):
            reply = dungeon_flow.periodic(self.session)
        self.assertEqual([e.kind for e in reply], [0xbc, 0xc1])
        self.assertEqual(cleared, [(7, 0)])
        self.assertTrue(self.session.clear_notified)
        self.assertIsNone(self.session.pending_part_end)

    def test_without_a_request_the_native_notice_still_comes_first(self):
        run = self.enter(SIGHT, 7)
        for key in self.boss_keys(8155, 8156):
            run.defeated[key] = b'\0'
        self.assertEqual(dungeon_flow.periodic(self.session), [])
        self.clock.value += 6
        reply = dungeon_flow.periodic(self.session)
        self.assertEqual([e.kind for e in reply], [0xba])
        self.assertTrue(self.session.part_end_notified)
        self.assertEqual((run.stage, run.part), (7, 0))
        self.assertFalse(self.session.clear_notified)

    def test_held_request_completes_a_stage_transition(self):
        run = self.enter(SIGHT, 6)
        (boss,) = self.boss_keys(8157)
        run.defeated[boss] = b'\0'
        self.assertEqual(dungeon_flow.handle(self.session, part_end_request(0)), [])
        reply = dungeon_flow.periodic(self.session)
        self.assertEqual([e.kind for e in reply], [0xbc, 0xb2])
        self.assertEqual((run.stage, run.part), (7, 0))
        self.assertTrue(self.session.gate_stage_loading)
        self.assertFalse(self.session.dungeon_substage_synced)
        self.assertIsNone(self.session.pending_part_end)
        self.assertEqual(struct.unpack('>i', reply[1].payload[:4])[0], 7)

    def test_request_for_another_part_is_not_held(self):
        run = self.enter(SIGHT, 7)
        dungeon_flow.handle(self.session, part_end_request(1))
        self.assertIsNone(self.session.pending_part_end)
        self.assertEqual((run.stage, run.part), (7, 0))

    def test_dummy_and_boss_rows_of_the_pinned_rooms_are_unchanged(self):
        self.enter(SIGHT, 7)
        dummies = [n for n in self.run.current['npcs'] if n['template'] == 8260]
        self.assertEqual(len(dummies), 2)
        self.assertTrue(all(local_dungeon_flow.dummy_hostile(self.run, n) for n in dummies))
        self.enter(PORTRAIT, 2)
        dummy = next(n for n in self.run.current['npcs'] if n['template'] == 8262)
        self.assertTrue(local_dungeon_flow.dummy_hostile(self.run, dummy))


if __name__ == '__main__':
    unittest.main(verbosity=2)
