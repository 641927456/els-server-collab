"""普鲁纳姆外围 (Devildom Side 34710/34720/34730) must settle.

Three source shapes reach ``condition_ready`` and can never be satisfied there:

* 34720 stage2 part0 and 34710 stage7 part0 close with ``kind == 0`` ("every
  live hostile is dead") while declaring class-103 ``IS_NPC`` stand-ins as
  ``active``. The client retires those inside its own scene, so no 0xad combat
  report ever arrives: the real boss dies, the part never ends, and the client's
  0xbb is dropped - no portal, no clear record, no settlement.
* 34710 stage0 part1 and stage4 part0 are branching rooms whose only actors are
  the ``关卡N触发对象`` templates 8168/8169/8170 (stage 1/2/3) and 8171/8172
  (stage 5/6). They are declared ``active=false`` and are named by ``kind == 3``
  exit conditions, so neither the combat path nor ``script_gate`` (which needs
  one live hostile) can open them, and the run never leaves the first junction.

Both families are admitted only through a pinned row: dungeon, stage, part, the
whole declared source row (template, source_index, points, gage, team, no_drop,
...), the graph ``source_sha256``, the script sha in the route manifest, and the
native ``class_id 103`` / ``IS_NPC`` identity. Every real boss of the same room
still has to die.

34710 stage1 is deliberately not an exit: its only actors are five 8211
``特殊型怪物_爆弹`` summon stand-ins, and the server refuses dynamic spawns
outside the population harness, so the room has no server-side fight at all.
The run therefore takes the stage-2 trigger instead of the stage-1 trigger.
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

SIDE1, SIDE2, SIDE3 = 34710, 34720, 34730


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


class DevildomSideExits(unittest.TestCase):
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

    def billable(self):
        """Live hostiles the room really owes a death report for."""
        return [n for n in self.live() if not local_dungeon_flow.dummy_hostile(self.run, n)]

    def kill(self, npc):
        self.run.defeated[npc['key']] = b'\0'

    def kill_billable(self):
        for npc in self.billable():
            self.kill(npc)

    def ready(self):
        """Arm the source condition (fixes ``ready_at``), then let its delay elapse."""
        self.run.poll_ready()
        self.clock.value += 10
        return self.run.poll_ready()

    # -- the pinned rows must describe the graph exactly -------------------
    def test_every_dummy_row_matches_its_graph(self):
        self.assertGreater(len(local_dungeon_flow.DUMMY_HOSTILE_SOURCES), 0)
        catalog = dungeon_routes.route_catalog()
        for row in local_dungeon_flow.DUMMY_HOSTILE_SOURCES:
            identity, stage, part = row['identity'], row['stage'], row['part']
            with self.subTest(dungeon=identity, stage=stage, part=part):
                graph = catalog.graph(identity)
                self.assertEqual(graph['source_sha256'], row['graph_sha'])
                self.assertGreater(len(row['sources']), 0)
                declared = [n for group in graph['stages'][str(stage)]['parts'][str(part)]['groups']
                            for n in group['npcs']]
                for pinned in row['sources']:
                    source = pinned['source']
                    native = client_data().npc(source['template'])
                    self.assertEqual(native['class_id'], pinned['class_id'])
                    self.assertIs(native['is_npc'], True)
                    self.assertEqual(native['script'], pinned['script'])
                    self.assertEqual(catalog.manifest['source_sha256'][pinned['script']],
                                     pinned['script_sha'])
                    hits = [n for n in declared if n.get('template') == source['template']
                            and n.get('source_index') == source['source_index']]
                    self.assertTrue(hits)
                    for hit in hits:
                        self.assertTrue(all(hit.get(k) == v for k, v in source.items()
                                            if k != 'active'))
                        # A waived stand-in must stay on the hostile team.
                        self.assertIs(hit['active'], True)
                        self.assertEqual(hit.get('team', 1), 1)
                        self.assertIs(hit.get('ally'), False)

    # -- 34720: the proven stall ------------------------------------------
    def test_side2_final_room_needs_its_boss_not_the_drop_dummy(self):
        self.enter(SIDE2, 2, 0)
        self.assertEqual(sorted(n['template'] for n in self.live()), [8176, 8262])
        self.assertEqual([n['template'] for n in self.billable()], [8176])
        self.assertFalse(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], -1)
        self.kill(self.billable()[0])
        self.assertTrue(self.ready())
        self.assertEqual(self.run.next['kind'], 4)

    # -- 34710: two costumes beside the final boss pair -------------------
    def test_side1_final_room_needs_both_bosses_not_the_costumes(self):
        self.enter(SIDE1, 7, 0)
        self.assertEqual(sorted(n['template'] for n in self.live()),
                         [8155, 8156, 8260, 8260])
        self.assertEqual(sorted(n['template'] for n in self.billable()), [8155, 8156])
        self.assertFalse(self.ready())
        self.kill(self.billable()[0])
        self.assertFalse(self.ready())
        self.kill(self.billable()[0])
        self.assertTrue(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)
        self.assertTrue(self.session.part_end_notified)

    # -- 34710: the two branching rooms ------------------------------------
    def test_side1_stage0_takes_the_stage2_trigger(self):
        self.enter(SIDE1, 0, 1)
        self.assertEqual(self.live(), [])
        conditions = self.run.current['conditions']
        self.assertEqual([tuple(c['required']) for c in conditions],
                         [(8168,), (8169,), (8170,)])
        self.assertTrue(self.ready())
        self.assertEqual(self.run.next['stage'], 2)
        self.assertEqual(self.run.advance(), 'stage')
        self.assertEqual((self.run.stage, self.run.part), (2, 0))

    def test_side1_stage0_trigger_1_is_not_an_exit(self):
        self.enter(SIDE1, 0, 1)
        marker = next(n for n in self.run.current['npcs'] if n['template'] == 8168)
        self.assertTrue(local_dungeon_flow.part_marker_npc(self.run, marker))
        # It is pinned (so the 0xb8 fence admits it) but never an exit: the run
        # must not drop into the summon-only stage 1.
        self.assertFalse(local_dungeon_flow.part_marker_gate(
            self.run, self.run.current['npcs'], set(), [8168]))

    def test_side1_stage4_takes_the_stage5_trigger(self):
        self.enter(SIDE1, 4, 0)
        self.assertEqual(self.live(), [])
        self.assertTrue(self.ready())
        self.assertEqual(self.run.next['kind'], 0)
        self.assertEqual((self.run.next['stage'], self.run.next['part']), (4, 1))
        self.assertEqual(self.run.advance(), 'part')
        self.assertEqual((self.run.stage, self.run.part), (4, 1))

    # -- 34710 stage4 part1: the sealed 8162 at point 14 -------------------
    # The room declares six 8162 DEVILDOM_SIDE1_SPECIAL spawns. Live evidence
    # (20261030-233948 and 20261031-105444) shows the point-14 instance is
    # created inside the sealed gate and never damaged: the other five 8162s and
    # every other hostile report 0xad while it keeps its untouched 1000 hp until
    # the map unloads. Only that declared row is waived; the other 13 hostiles
    # still gate the room.
    def test_side1_stage4_wave_settles_with_the_sealed_special_alive(self):
        self.enter(SIDE1, 4, 1)
        sealed = next(n for n in self.run.current['npcs']
                      if n['template'] == 8162 and n['start_point'] == 14)
        self.assertEqual((sealed['source_index'], sealed['team']), (13, 1))
        self.assertTrue(local_dungeon_flow.dummy_hostile(self.run, sealed))
        # Its five siblings and every other hostile are still billable.
        billable = self.billable()
        self.assertEqual(len(billable), 13)
        self.assertFalse(any(n['template'] == 8162 and n['start_point'] == 14
                             for n in billable))
        self.assertEqual(len([n for n in billable if n['template'] == 8162]), 5)
        # Nothing dead: the room stays shut and 0xb8 is refused.
        self.assertFalse(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(1))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], -1)
        # Every other hostile dead, the sealed one still standing: it settles.
        self.kill_billable()
        self.assertIn(sealed['key'], {n['key'] for n in self.live()})
        self.assertTrue(self.ready())
        self.assertEqual((self.run.next['stage'], self.run.next['part']), (4, 2))
        reply = dungeon_flow.handle(self.session, portal_request(1))
        self.assertEqual([event.kind for event in reply][:2], [0xb9, 0xba])
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)
        self.assertTrue(self.session.part_end_notified)

    def test_side1_sealed_special_waiver_is_pinned_to_its_own_row(self):
        self.enter(SIDE1, 4, 1)
        sealed = next(n for n in self.run.current['npcs']
                      if n['template'] == 8162 and n['start_point'] == 14)
        for forged in (dict(sealed, start_point=6), dict(sealed, source_index=12),
                       dict(sealed, team=0), dict(sealed, start_point=16)):
            self.assertFalse(local_dungeon_flow.dummy_hostile(self.run, forged))
        # With the row switched off the room really does wait for it.
        victims = self.billable()
        with patch.object(local_dungeon_flow, 'dummy_hostile', lambda run, npc: False):
            for npc in victims:
                self.kill(npc)
            self.assertFalse(self.ready())

    def test_side1_branching_room_is_acknowledged_by_the_client_request(self):
        self.enter(SIDE1, 0, 1)
        self.assertTrue(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(1))
        self.assertEqual(reply[0].kind, 0xb9)
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)
        self.assertTrue(self.session.part_end_notified)
        reply = dungeon_flow.handle(
            self.session, Event(0x202, kind=0xbb, payload=struct.pack('>b', 1)))
        self.assertEqual([event.kind for event in reply][:2], [0xbc, 0xb2])
        self.assertEqual((self.run.stage, self.run.part), (2, 0))

    # -- end to end --------------------------------------------------------
    def walk(self, identity):
        self.enter(identity, 0, 0)
        visited = []
        for _ in range(40):
            # A kind-0 sub-part keeps the stage but resets the ready clock, so
            # every entry re-arms it exactly like the 0xbb handler does.
            self.run.loaded()
            visited.append((self.run.stage, self.run.part))
            self.kill_billable()
            if not self.ready():
                self.fail('part %r never satisfies its condition' % (visited[-1],))
            if self.run.next['kind'] == 4:
                return visited, 'clear'
            self.run.advance()
        self.fail('run never settled: %r' % (visited[-1],))

    def test_side1_walks_to_a_clear(self):
        visited, verdict = self.walk(SIDE1)
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited, [(0, 0), (0, 1), (2, 0), (2, 1), (4, 0),
                                   (4, 1), (4, 2), (5, 0), (7, 0)])

    def test_side2_walks_to_a_clear(self):
        visited, verdict = self.walk(SIDE2)
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited[-1], (2, 0))

    def test_side3_walks_to_a_clear_without_any_relaxation(self):
        # 34730 closes with kind 3 on a real boss per room and needs no waiver.
        with patch.object(local_dungeon_flow, 'dummy_hostile', lambda run, npc: False), \
                patch.object(local_dungeon_flow, 'dummy_hostile_relaxation', lambda: False):
            visited, verdict = self.walk(SIDE3)
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited, [(0, 0), (1, 0), (2, 0)])

    # -- 34730's dormant crystals and statues ------------------------------
    # Waking them is not a fix. The client builds no entity for the
    # STAGE*_CRYSTAL*/*STATUE* scripts - the live save holds 108 kills of
    # 8267-8271 and none of 8193-8198/8273-8279 - and stage1/stage2 close on
    # class-103 markers, so their exit falls back to _room_clear, which would
    # then demand a death the client can never report.
    def test_side3_keeps_every_declared_non_boss_actor_dormant(self):
        for stage, part in ((0, 0), (1, 0), (2, 0)):
            with self.subTest(stage=stage, part=part):
                self.enter(SIDE3, stage, part)
                declared = [n for n in self.run.current['npcs']]
                self.assertGreater(len([n for n in declared if not n['boss']]), 0)
                self.assertFalse(any(n['active'] for n in declared if not n['boss']))

    def test_side3_stage1_and_stage2_close_on_their_boss_alone(self):
        self.enter(SIDE3, 1, 0)
        self.assertEqual([n['template'] for n in self.live()], [8191])
        self.kill_billable()
        self.assertTrue(self.ready())

    def test_waking_a_crystal_would_wedge_the_stage_one_exit(self):
        self.enter(SIDE3, 1, 0)
        for npc in self.live():
            self.kill(npc)
        self.assertTrue(self.ready())
        # Same room with one crystal flipped the way the old override did it:
        # the boss is dead and the exit still refuses to open.
        self.enter(SIDE3, 1, 0)
        for npc in self.live():
            self.kill(npc)
        next(n for n in self.run.current['npcs'] if n['template'] == 8196)['active'] = True
        self.assertFalse(self.ready())

    def test_side3_markers_and_drop_stand_in_stay_dormant(self):
        for stage, part, templates in ((0, 0, (8263,)), (1, 0, (8264, 8272, 8280, 8285)),
                                       (2, 0, (8265, 8266, 8200))):
            with self.subTest(stage=stage, part=part):
                self.enter(SIDE3, stage, part)
                for template in templates:
                    npc = next(n for n in self.run.current['npcs'] if n['template'] == template)
                    self.assertIs(npc['active'], False)
                    self.assertNotIn(npc['key'], {x['key'] for x in self.live()})

    # -- 34730 stage2: five boss bodies stacked on one point ----------------
    # 8192 (200 lines, 144e9 hp), 8201/8202/8203 (150 lines each) and 8282
    # (250 lines) all spawn on point 1 and the client composites them into one
    # body, so only the heart 8282 ever reports a death: the live save holds one
    # 8282 kill and none of the other four. The room has to settle on the heart
    # and waive the body parts from the fence.
    def test_side3_stage2_settles_on_the_heart(self):
        self.enter(SIDE3, 2, 0)
        self.kill(next(n for n in self.run.current['npcs'] if n['template'] == 8282))
        self.assertTrue(self.ready())
        # The body is still standing, exactly as it is in game.
        self.assertIn(8192, [n['template'] for n in self.live()])
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(reply[0].kind, 0xb9)
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)
        self.assertTrue(self.session.part_end_notified)

    def test_side3_stage2_body_parts_are_waived_but_the_heart_is_not(self):
        self.enter(SIDE3, 2, 0)
        for template in (8192, 8201, 8202, 8203):
            npc = next(n for n in self.run.current['npcs'] if n['template'] == template)
            self.assertTrue(local_dungeon_flow.boss_core(self.run, npc))
        self.assertFalse(local_dungeon_flow.boss_core(
            self.run, next(n for n in self.run.current['npcs'] if n['template'] == 8282)))
        # Nothing dead yet: the room must not open, and 0xb8 must be refused.
        self.assertFalse(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], -1)

    def test_the_heart_waiver_is_pinned_to_its_own_room(self):
        for stage, template in ((0, 8190), (1, 8191)):
            with self.subTest(stage=stage):
                self.enter(SIDE3, stage, 0)
                npc = next(n for n in self.run.current['npcs'] if n['template'] == template)
                self.assertFalse(local_dungeon_flow.boss_core(self.run, npc))
                self.assertFalse(local_dungeon_flow.boss_core_cleared(self.run))

    # -- 34730 stage1: the summoned wave must be told to build a body -------
    # The client asks for a summon with 0x4e clear and then draws nothing: the
    # monster keeps its hitbox and still reports its death, so it fights
    # invisibly. The static population path always ships the flag set, which is
    # why 34710 renders and this summon does not.
    def test_a_summoned_monster_is_replied_active_but_stays_out_of_the_clear(self):
        from els_server.domain import dungeon_spawns
        from els_server.domain.dungeon_npcs import encode_npc
        self.enter(SIDE3, 1, 0)
        self.session.population_test = True
        dto = bytearray(0xa4)
        struct.pack_into('<ii', dto, 0, -1, 8267)
        struct.pack_into('<fff', dto, 9, 0.0, 0.0, 0.0)
        struct.pack_into('<i', dto, 0x4f, -1)
        struct.pack_into('<Q', dto, 0x6d, 0)
        dto[8] = 1
        dto[0x4e] = 0
        dto[0x53] = 100
        payload = struct.pack('>I', 1) + encode_npc(dto, 0)
        reply = dungeon_spawns.handle(self.session, Event(0x202, kind=0x2ce, payload=payload), 1)
        self.assertIsNotNone(reply)
        packet = reply[1]
        self.assertEqual(packet.kind, 0x2d0)
        rows = dungeon_spawns.decode(struct.pack('>I', 1) + packet.payload[4:4 + 116], lambda d: None)
        self.assertEqual(rows[0][0x4e], 1, 'the reply has to ask for a body')
        spawned = self.run.current['npcs'][-1]
        self.assertEqual(spawned['template'], 8267)
        self.assertIs(spawned['active'], False, 'the roster keeps the flag the client sent')

    def test_summon_activation_switch_off_keeps_the_client_flag(self):
        from els_server.domain import dungeon_spawns
        from els_server.domain.dungeon_npcs import encode_npc
        self.enter(SIDE3, 1, 0)
        self.session.population_test = True
        dto = bytearray(0xa4)
        struct.pack_into('<ii', dto, 0, -1, 8267)
        struct.pack_into('<fff', dto, 9, 0.0, 0.0, 0.0)
        struct.pack_into('<i', dto, 0x4f, -1)
        struct.pack_into('<Q', dto, 0x6d, 0)
        dto[8] = 1
        dto[0x4e] = 0
        dto[0x53] = 100
        payload = struct.pack('>I', 1) + encode_npc(dto, 0)
        with patch.object(local_dungeon_flow, 'summon_activation', lambda: False):
            reply = dungeon_spawns.handle(self.session, Event(0x202, kind=0x2ce, payload=payload), 1)
        rows = dungeon_spawns.decode(struct.pack('>I', 1) + reply[1].payload[4:4 + 116], lambda d: None)
        self.assertEqual(rows[0][0x4e], 0)

    # -- identity pinning --------------------------------------------------
    def test_a_forged_costume_copy_is_refused(self):
        self.enter(SIDE1, 7, 0)
        npc = next(n for n in self.run.current['npcs'] if n['template'] == 8260)
        self.assertTrue(local_dungeon_flow.dummy_hostile(self.run, npc))
        self.assertFalse(local_dungeon_flow.dummy_hostile(self.run, dict(npc, start_point=99)))
        self.assertFalse(local_dungeon_flow.dummy_hostile(self.run, dict(npc, team=0)))
        self.assertFalse(local_dungeon_flow.dummy_hostile(self.run, dict(npc, source_index=1)))
        # The real boss pair is never admitted.
        boss = next(n for n in self.run.current['npcs'] if n['template'] == 8155)
        self.assertFalse(local_dungeon_flow.dummy_hostile(self.run, boss))

    def test_a_pinned_costume_outside_its_own_room_is_refused(self):
        # stage5 declares the same 8260 costume, but as active=false: it is not
        # a live hostile there, so nothing is waived and the boss still closes.
        self.enter(SIDE1, 5, 0)
        npc = next(n for n in self.run.current['npcs'] if n['template'] == 8260)
        self.assertIs(npc['active'], False)
        self.assertFalse(local_dungeon_flow.dummy_hostile(self.run, npc))
        self.assertEqual([n['template'] for n in self.billable()], [8158])
        self.assertFalse(self.ready())
        self.kill(self.billable()[0])
        self.assertTrue(self.ready())

    def test_a_forged_trigger_is_refused(self):
        self.enter(SIDE1, 0, 1)
        marker = next(n for n in self.run.current['npcs'] if n['template'] == 8169)
        self.assertTrue(local_dungeon_flow.part_marker_npc(self.run, marker))
        self.assertFalse(local_dungeon_flow.part_marker_npc(
            self.run, dict(marker, start_point=1)))
        self.assertFalse(local_dungeon_flow.part_marker_npc(
            self.run, dict(marker, source_index=1)))

    # -- switches ----------------------------------------------------------
    def test_switches_off_restore_the_stall(self):
        self.enter(SIDE1, 0, 1)
        with patch.object(local_dungeon_flow, 'part_marker_relaxation', lambda: False):
            self.assertFalse(self.ready())
            self.assertFalse(self.session.part_end_notified)
            self.assertEqual((self.run.stage, self.run.part), (0, 1))
        self.enter(SIDE1, 7, 0)
        with patch.object(local_dungeon_flow, 'dummy_hostile', lambda run, npc: False):
            self.kill(self.billable()[0])
            self.kill(self.billable()[0])
            self.assertFalse(self.ready())
        self.enter(SIDE2, 2, 0)
        with patch.object(local_dungeon_flow, 'dummy_hostile_relaxation', lambda: False):
            self.kill(self.billable()[0])
            self.assertFalse(self.ready())
        self.enter(SIDE3, 2, 0)
        self.kill(next(n for n in self.run.current['npcs'] if n['template'] == 8282))
        with patch.object(local_dungeon_flow, 'boss_core_relaxation', lambda: False):
            self.assertFalse(self.ready())


if __name__ == '__main__':
    unittest.main(verbosity=2)
