"""尼格摩尔 (Devildom2 34340/34350/34360) parts must open after their fight.

Regression: four rooms close with ``{"kind": 3, "required": [<class-103 marker>]}``
instead of naming a monster.

* 34340 stage0 part1 requires 7587 (``DEVILDOM2_RESIDENCE_STAGE1_START.lua``,
  declared ``active=false``); it is the room's only actor.
* 34350 stage0 part0 requires 7568 (``..._STAGE0_CLEAR``) and stage1 part0
  requires 7570 (``..._STAGE1_DUMMY``) beside the 7553 boss-event marker.
* 34360 stage1 part0 requires 7605 (``..._STAGE1_END``) and stage2 part0
  requires 7607 (``..._STAGE2_END``).

All five templates are ``class_id 103`` with ``IS_NPC`` true, so the client
retires them inside its own scene. Session 20261029-215610 shows the shape:
34340 part1 loaded 7587, then the client destroyed it without a single 0xad
report and its 0xb8 portal request was answered ``result=-1`` (the previous
34360 room's boss 7593 was still alive, which is correct). The server's kind-3
branch required that marker to be in ``run.defeated``, which can never happen,
and ``script_gate`` needs at least one live hostile, which these rooms do not
have. The exit therefore never opened.

``part_marker_gate`` waives exactly the pinned markers of a pinned room and
still requires every other living actor to be dead, so the real bosses 7551
(34350 stage1) and 7593 (34360 stage0) keep their combat requirement.
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

RESIDENCE, FACTORY, PORTAL = 34340, 34350, 34360


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


def portal_request(part):
    return Event(0x202, kind=0xb8, payload=struct.pack('>b', part))


class Devildom2PartMarkers(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.run = None
        self.session = None

    def enter(self, identity, stage, part):
        self.clock.value = 100.0
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
                          summon_requests={}, summon_next_key=16,
                          defeated_npcs=self.run.defeated, application=None,
                          active_challenge=None, clear_items_synced=False)
        return self.run

    def live(self):
        return [n for n in self.run.current['npcs']
                if n['active'] and n.get('team', 1) != 0 and n['key'] not in self.run.defeated]

    def kill(self, npc):
        self.run.defeated[npc['key']] = b'\0'

    def kill_room_except(self, *templates):
        for npc in self.live():
            if npc['template'] not in templates:
                self.kill(npc)

    def ready(self):
        """Arm the source condition (fixes ``ready_at``), then let its delay elapse."""
        self.run.poll_ready()
        self.clock.value += 10
        return self.run.poll_ready()

    # -- the pinned rows must describe the graph exactly -------------------
    def test_every_pinned_row_matches_its_graph(self):
        self.assertGreater(len(local_dungeon_flow.PART_MARKERS), 0)
        catalog = self.run.catalog if self.run else dungeon_routes.route_catalog()
        for (identity, stage, part), row in local_dungeon_flow.PART_MARKERS.items():
            with self.subTest(dungeon=identity, stage=stage, part=part):
                graph = catalog.graph(identity)
                self.assertEqual(graph['source_sha256'], row['graph_sha'])
                conditions = graph['stages'][str(stage)]['parts'][str(part)]['conditions']
                self.assertEqual(len(conditions), 1)
                self.assertEqual(conditions[0]['kind'], 3)
                self.assertEqual(tuple(conditions[0]['required']), row['required'])
                groups = graph['stages'][str(stage)]['parts'][str(part)]['groups']
                # A part may carry several draw groups plus an empty fallback;
                # each group that draws an actor declares it once.
                def declares(group, template, source_index=None):
                    return [n for n in group['npcs']
                            if n.get('template') == template
                            and (source_index is None or n.get('source_index') == source_index)]
                for group in groups:
                    self.assertLessEqual(len(declares(group, row['required'][0])), 1)
                self.assertTrue(any(declares(g, row['required'][0]) for g in groups))
                for marker in row['markers']:
                    source = marker['source']
                    native = client_data().npc(source['template'])
                    self.assertEqual(native['class_id'], 103)
                    self.assertIs(native['is_npc'], True)
                    self.assertEqual(native['script'], marker['script'])
                    self.assertEqual(catalog.manifest['source_sha256'][marker['script']],
                                     marker['script_sha'])
                    hits = [n for group in groups
                            for n in declares(group, source['template'], source['source_index'])]
                    self.assertTrue(hits)
                    for hit in hits:
                        self.assertEqual(hit['points'], source['points'])

    def test_each_room_runtime_roster_declares_its_markers(self):
        for identity, stage, part in ((RESIDENCE, 0, 1), (FACTORY, 0, 0), (FACTORY, 1, 0),
                                      (PORTAL, 0, 0), (PORTAL, 1, 0), (PORTAL, 2, 0)):
            with self.subTest(dungeon=identity, stage=stage, part=part):
                self.enter(identity, stage, part)
                row = local_dungeon_flow.PART_MARKERS[(identity, stage, part)]
                for marker in row['markers']:
                    source = marker['source']
                    hits = [n for n in self.run.current['npcs']
                            if n['template'] == source['template']]
                    self.assertEqual(len(hits), 1)
                    self.assertEqual(hits[0]['start_point'], source['points'][0])
                    self.assertTrue(local_dungeon_flow.part_marker_npc(self.run, hits[0]))

    # -- the proven stall -------------------------------------------------
    def test_residence_gate_opens_without_a_death_report(self):
        self.enter(RESIDENCE, 0, 1)
        self.assertEqual(self.live(), [])
        self.assertEqual(self.run.defeated, {})
        self.assertTrue(self.ready())
        self.assertEqual(self.run.advance(), 'stage')
        self.assertEqual((self.run.stage, self.run.part), (1, 0))

    def test_residence_portal_request_is_acknowledged(self):
        self.enter(RESIDENCE, 0, 1)
        self.ready()
        reply = dungeon_flow.handle(self.session, portal_request(1))
        self.assertEqual(reply[0].kind, 0xb9)
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)
        self.assertTrue(self.session.part_end_notified)

    def test_residence_transition_request_loads_the_next_stage(self):
        self.enter(RESIDENCE, 0, 1)
        self.ready()
        dungeon_flow.handle(self.session, portal_request(1))
        reply = dungeon_flow.handle(
            self.session, Event(0x202, kind=0xbb, payload=struct.pack('>b', 1)))
        self.assertEqual([event.kind for event in reply][:2], [0xbc, 0xb2])
        self.assertEqual((self.run.stage, self.run.part), (1, 0))
        self.assertTrue(self.session.gate_stage_loading)
        self.assertEqual(struct.unpack('>i', reply[1].payload[:4])[0], 1)

    # -- the factory: a clear marker room and a boss room -----------------
    def test_factory_clear_marker_opens_its_room_on_entry(self):
        self.enter(FACTORY, 0, 0)
        self.assertEqual([n['template'] for n in self.live()], [7568])
        self.assertTrue(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)
        self.assertTrue(self.session.part_end_notified)

    def test_factory_boss_room_still_needs_the_boss(self):
        self.enter(FACTORY, 1, 0)
        boss = [n for n in self.live() if n['template'] == 7551]
        self.assertEqual(len(boss), 1)
        self.assertFalse(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], -1)
        self.kill(boss[0])
        # The 7570 dummy and the 7553 boss-event markers stay alive.
        self.assertEqual(sorted(n['template'] for n in self.live()), [7553, 7570])
        self.assertTrue(self.ready())

    # -- the portal: real hostiles keep their requirement -----------------
    def test_portal_stage1_needs_every_real_hostile(self):
        self.enter(PORTAL, 1, 0)
        hostiles = [n for n in self.live() if n['template'] != 7605]
        self.assertEqual(len(hostiles), 14)
        self.assertFalse(self.ready())
        self.kill_room_except(7605)
        self.assertEqual([n['template'] for n in self.live()], [7605])
        self.assertTrue(self.ready())

    def test_portal_stage2_needs_its_boss(self):
        self.enter(PORTAL, 2, 0)
        boss = [n for n in self.live() if n['template'] == 7601]
        self.assertEqual(len(boss), 1)
        self.assertFalse(self.ready())
        self.kill(boss[0])
        self.assertEqual([n['template'] for n in self.live()], [7607])
        self.assertTrue(self.ready())

    def test_portal_stage0_marker_is_waived_but_its_boss_is_not(self):
        self.enter(PORTAL, 0, 0)
        self.assertEqual(self.run.current['conditions'][0]['required'], [7593])
        self.kill_room_except(7593, 7603)
        # 7593 is a real boss (class 0), so the kind-3 requirement stands.
        self.assertFalse(self.ready())
        boss = next(n for n in self.run.current['npcs'] if n['template'] == 7593)
        self.kill(boss)
        # 7603 is a class-103 end marker: never reported, but waived.
        self.assertEqual([n['template'] for n in self.live()], [7603])
        self.assertTrue(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)

    # -- identity pinning --------------------------------------------------
    def test_a_marker_copy_with_a_wrong_source_point_is_refused(self):
        self.enter(PORTAL, 1, 0)
        marker = next(n for n in self.run.current['npcs'] if n['template'] == 7605)
        self.assertTrue(local_dungeon_flow.part_marker_npc(self.run, marker))
        forged = dict(marker, start_point=marker['start_point'] + 1)
        self.assertFalse(local_dungeon_flow.part_marker_npc(self.run, forged))
        forged = dict(marker, no_drop=False)
        self.assertFalse(local_dungeon_flow.part_marker_npc(self.run, forged))

    def test_an_unpinned_room_is_not_admitted(self):
        self.assertNotIn((RESIDENCE, 1, 0), local_dungeon_flow.PART_MARKERS)
        self.enter(RESIDENCE, 1, 0)
        self.assertTrue(self.live())
        self.assertFalse(any(local_dungeon_flow.part_marker_npc(self.run, n)
                             for n in self.run.current['npcs']))
        # A pinned template outside its own room is not admitted either.
        self.enter(FACTORY, 0, 0)
        self.assertFalse(local_dungeon_flow.part_marker_gate(
            self.run, self.run.current['npcs'], set(), [7570]))

    def test_a_living_unpinned_hostile_blocks_the_gate(self):
        self.enter(FACTORY, 1, 0)
        boss = next(n for n in self.run.current['npcs'] if n['template'] == 7551)
        alien = dict(self.run.current['npcs'][0], key=99, template=200)
        npcs = self.run.current['npcs'] + [alien]
        self.assertFalse(local_dungeon_flow.part_marker_gate(
            self.run, npcs, {boss['key']}, [7570]))
        self.assertTrue(local_dungeon_flow.part_marker_gate(
            self.run, npcs, {boss['key'], 99}, [7570]))

    def test_switch_off_restores_the_stall(self):
        self.enter(RESIDENCE, 0, 1)
        with patch.object(local_dungeon_flow, 'part_marker_relaxation', lambda: False):
            self.assertFalse(self.ready())
            self.assertFalse(self.session.part_end_notified)
            reply = dungeon_flow.handle(
                self.session, Event(0x202, kind=0xbb, payload=struct.pack('>b', 1)))
            self.assertFalse(reply)
            self.assertEqual((self.run.stage, self.run.part), (0, 1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
