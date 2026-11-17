"""Devildom1 Henir (34090) room 2/1: the client owns the wave, the gate must not.

Three recorded visits pin the native part runtime down: the roster has to stay at
its declared length because the client resolves a spawn through the declared
NPC_POINT array, and only source_index 12..16 ever become actors. These tests
keep the roster dense, keep the clear condition on the reachable five, and pin
the local post-clear window that ends the respawn loop.
"""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import dungeon_flow
from els_server.domain import dungeon_routes
from els_server.domain.dungeon_routes import DungeonRun

IDENTITY = 34090
SHA = '57f327e11988b929cbf655cf07f1ca51c1501970bc5113db14f65ce9c1a49ffb'
REACHABLE = (27, 28, 29, 30, 31)


def room(stage, part):
    """A run parked on one room of the pinned graph, as if the client had loaded it."""
    run = DungeonRun(IDENTITY, 'c3f2f0d4-6d2b-4c2a-9b7e-5a1f0d8e4b21')
    run._load_stage(stage)
    run.part = part
    run.loaded()
    return run


class Devildom1HenirRoomTests(unittest.TestCase):
    def test_room_2_1_keeps_its_declared_roster_length(self):
        # Compaction is what broke the room: the client resolves a spawn through
        # the declared NPC_POINT array, so a five-row roster materialised nothing.
        run = room(2, 1)
        rows = run.current['npcs']
        self.assertEqual([n['start_point'] for n in rows], list(range(1, 18)))
        self.assertEqual([n['key'] for n in rows], list(range(16, 33)))
        self.assertEqual([n['source_index'] for n in rows], list(range(1, 18)))
        self.assertEqual([n['template'] for n in rows],
                         [6503]*9+[6505]*3+[6503]*3+[6504]*2)

    def test_clear_condition_only_demands_the_five_the_client_builds(self):
        run = room(2, 1)
        self.assertEqual([n['key'] for n in run.gate_npcs()], list(REACHABLE))
        self.assertFalse(run.condition_ready(run.current['conditions'][0]))
        for key in REACHABLE[:-1]:
            run.defeated[key] = b'\0'*10
        self.assertFalse(run.condition_ready(run.current['conditions'][0]))
        run.defeated[REACHABLE[-1]] = b'\0'*10
        self.assertTrue(run.condition_ready(run.current['conditions'][0]))
        self.assertTrue(run.poll_ready())
        self.assertEqual((run.next['stage'], run.next['part']), (2, 2))
        self.assertEqual(run.advance(), 'part')
        self.assertEqual((run.stage, run.part), (2, 2))

    def test_the_part_before_it_still_needs_every_hostile(self):
        # The relaxation is pinned to one room; part 0 keeps its untouched gate.
        run = room(2, 0)
        rows = run.current['npcs']
        self.assertEqual([n['key'] for n in run.gate_npcs()], list(range(16)))
        self.assertEqual(len(rows), 16)
        for key in range(15):
            run.defeated[key] = b'\0'*10
        self.assertFalse(run.condition_ready(run.current['conditions'][0]))
        run.defeated[15] = b'\0'*10
        self.assertTrue(run.condition_ready(run.current['conditions'][0]))

    def test_a_mutated_graph_keeps_the_untouched_source_gate(self):
        run = room(2, 1)
        run.graph = {**run.graph, 'source_sha256': '0'*64}
        self.assertEqual(len(run.gate_npcs()), 17)

    def test_other_rooms_are_untouched(self):
        run = room(6, 0)
        self.assertEqual(run.gate_npcs(),
                         [n for n in run.current['npcs']
                          if n['active'] and n.get('team', 1) != 0])


class PostClearWindowTests(unittest.TestCase):
    def test_window_starts_after_the_last_hostile_and_never_before(self):
        run = room(2, 1)
        session = NS()
        for key in REACHABLE[:-1]:
            run.defeated[key] = b'\0'*10
        self.assertFalse(dungeon_flow._post_clear_waited(session, run))
        self.assertIsNone(session.part_clear_mark)
        run.defeated[REACHABLE[-1]] = b'\0'*10
        self.assertFalse(dungeon_flow._post_clear_waited(session, run))
        self.assertEqual(session.part_clear_mark[:3], (2, 1, run.visits))
        with patch.object(dungeon_flow, 'STUCK_CLEAR_SECONDS', 0.0):
            self.assertTrue(dungeon_flow._post_clear_waited(session, run))

    def test_a_new_wave_restarts_the_window(self):
        run = room(2, 1)
        session = NS()
        for key in REACHABLE:
            run.defeated[key] = b'\0'*10
        dungeon_flow._post_clear_waited(session, run)
        self.assertIsNotNone(session.part_clear_mark)
        run.current['npcs'].append({'key': 40, 'template': 6503, 'active': True, 'team': 1,
                                    'no_drop': False, 'ally': False, 'boss': False})
        with patch.object(dungeon_flow, 'STUCK_CLEAR_SECONDS', 0.0):
            self.assertFalse(dungeon_flow._post_clear_waited(session, run))
        self.assertIsNone(session.part_clear_mark)

    def test_the_fallback_takes_the_parts_own_declared_exit(self):
        # No synthesized destination: force_ready selects the condition's target.
        run = room(2, 1)
        for key in REACHABLE:
            run.defeated[key] = b'\0'*10
        with patch.object(DungeonRun, 'condition_ready', return_value=False):
            self.assertFalse(run.poll_ready())
            self.assertTrue(run.force_ready())
        self.assertEqual((run.next['kind'], run.next['stage'], run.next['part']), (0, 2, 2))
        self.assertEqual(run.advance(), 'part')

    def test_an_empty_part_never_opens_by_itself(self):
        # stage 2 part 2 is the seven-second exit corridor: a timer room.
        run = room(2, 2)
        self.assertEqual(run.gate_npcs(), [])
        with patch.object(dungeon_flow, 'STUCK_CLEAR_SECONDS', 0.0):
            self.assertFalse(dungeon_flow._post_clear_waited(NS(), run))
        self.assertFalse(run.poll_ready())


if __name__ == '__main__':
    unittest.main()
