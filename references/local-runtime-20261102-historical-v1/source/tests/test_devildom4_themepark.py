"""缇尔诺格 (Devildom4) theme park dungeon set must settle.

The five routes pickable from the 主题公园入口 are 34760 主题公园, 34770 戏法屋,
34780 傀儡剧场, 34790 狂乱的演唱会 and 34800 影子伯爵的城堡. Three source shapes
reach ``condition_ready`` and can never be satisfied there:

* 34770 stage0/stage3 and 34800 stage1/stage3 close with ``kind == 0`` ("every
  live hostile is dead") while declaring an active class-103 ``IS_NPC``
  stand-in (8345 ``DM_DUMMY``, 8399/8400/8401 ``LEVER_MANAGER_n``). The client
  retires those inside its own scene, so no 0xad report ever arrives and the
  room never settles. The 34800 lever shape is proven by the live run
  ``9fd8df0c-a40c-40c6-96a7-56aab4c89cf8``: stage1 part0 holds kill records for
  keys 0-7 only, and the lever manager is key 8.
* 34760 stage3 names 8412 ``DROP_DUMMY``, 34770 stage2 names the same 8345,
  34770 stage5 names 8344 ``BOSS_END`` and 34800 stage2 names 8432
  ``CLEAR_DUMMY``/8397 ``BOSS_MIDDLE_END`` in ``kind == 3`` conditions. These
  are class-103 markers, not monsters, and the client never reports their
  retirement.
* 34780 stage2 closes on the 8359 script door (``kind == 3``) while declaring
  the class-103 boss hands 8361/8362 as active hostiles. The door is waived by
  ``script_gate`` already, but its room-clear check counted the hands.
* 34780 stage0 part2 closes with ``kind == 5`` and never sees the client's
  portal request: its only 0xb8 in run ``20261031-150518`` was the queued tail
  of the previous part transition (0.2 s after 0xbd, rejected as unsynced) and
  no further request arrived in the 17 minutes after the last kill. 462 of 462
  0xbb part-end requests in that session follow a server 0xba, so without the
  notice the client never advances. ``PORTAL_EXITS`` pins that one room and
  settles it on its own clear, exactly like ``kind == 0``.

Every waiver is a pinned row: dungeon, stage, part, the whole declared source
row (template, source_index, points, gage, team, no_drop, ...), the graph
``source_sha256`` and the script sha in the route manifest. A real boss or mob
of the same room still has to die.

34760 stage2 is different: it is a summon arena whose only declared actor is
8291 ``DEVILDOM4_THEMEPARK_SUMMON.lua``. Its waves arrive through 0x2ce and are
recorded with the client's clear flag, so the declared roster never holds a
live hostile. Waiving the manager would make the fence empty and end the part
the instant the room loads, before the arena is fought; the pinned row therefore
carries ``portal`` and settles only on the client's own 0xb8, exactly like a
``kind == 5`` room.

34790 needs no waiver at all: stage0 is a 160 second timer and stage1 closes on
the real boss 8370.

34760 stage0 part1 is the one room where plain combat monsters leave through
the client's native flag-255 expiry: in 20261031-132142 only two of the 39
size-160 reports lack a dynamic balloon to pair with (05:32:44.152 and
05:32:52.620), and the two 8288 INCUBUS at points 29/31 are the only declared
actors that never report a combat death. ``NATIVE_EXPIRY_ROOMS`` admits that
exact room/template shape with its initialized HP and acknowledges it, so the
kind==0 fence can see them dead. 34770 stage0/stage4-part1 additionally declare
five/two active class-103 8308 ``BOX`` breakables that are waived like the
other scene stand-ins.
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

THEMEPARK = (34760, 34770, 34780, 34790, 34800)


class FakeClock:
    def __init__(self):
        self.value = 100.0
        self.started = 0.0
        self.total = 0.0

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


class Devildom4ThemePark(unittest.TestCase):
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
        return [n for n in self.live()
                if not local_dungeon_flow.dummy_hostile(self.run, n)
                and not local_dungeon_flow.part_marker_npc(self.run, n)]

    def kill(self, npc):
        self.run.defeated[npc['key']] = b'\0'

    def kill_billable(self):
        for npc in self.billable():
            self.kill(npc)

    def ready(self):
        """Arm the source condition (fixes ``ready_at``), then let its delay elapse."""
        self.run.poll_ready()
        self.clock.value += 200
        return self.run.poll_ready()

    # -- the pinned rows must describe the graph exactly -------------------
    def test_every_themepark_marker_row_matches_its_graph(self):
        catalog = dungeon_routes.route_catalog()
        rows = [(key, row) for key, row in local_dungeon_flow.PART_MARKERS.items()
                if key[0] in THEMEPARK]
        self.assertGreaterEqual(len(rows), 5)
        for (identity, stage, part), row in rows:
            with self.subTest(dungeon=identity, stage=stage, part=part):
                graph = catalog.graph(identity)
                self.assertEqual(graph['source_sha256'], row['graph_sha'])
                exits = set(row.get('exits') or row['required'])
                self.assertTrue(set(row['required']) <= exits)
                declared = [n for group in graph['stages'][str(stage)]['parts'][str(part)]['groups']
                            for n in group['npcs']]
                for marker in row['markers']:
                    source = marker['source']
                    native = client_data().npc(source['template'])
                    self.assertEqual(native['class_id'], 103)
                    self.assertIs(native['is_npc'], True)
                    self.assertEqual(native['script'], marker['script'])
                    self.assertEqual(catalog.manifest['source_sha256'][marker['script']],
                                     marker['script_sha'])
                    hits = [n for n in declared if n.get('template') == source['template']
                            and n.get('source_index') == source['source_index']]
                    self.assertTrue(hits)
                    for hit in hits:
                        self.assertTrue(all(hit.get(k) == v for k, v in source.items()
                                            if k != 'active'))

    # -- 34760: the summon arena and the drop dummy ------------------------
    def test_34760_summon_arena_waits_for_the_client_portal(self):
        self.enter(34760, 2, 0)
        self.assertEqual([n['template'] for n in self.live()], [8291])
        self.assertEqual(self.billable(), [])
        self.assertTrue(local_dungeon_flow.dummy_portal(self.run))
        # The fence is empty on arrival: the server must not end the part before
        # the arena is fought, so it waits for the client's own portal request.
        self.assertFalse(self.ready())
        self.assertEqual(dungeon_flow.periodic(self.session), [])
        local_dungeon_flow.arena_client_end(self.run)
        self.assertTrue(self.ready())
        self.assertEqual((self.run.next['stage'], self.run.next['part'],
                          self.run.next['kind']), (3, 0, 1))
        # Switching the waiver off reinstates the stall: the manager is the only
        # declared hostile and never reports.
        with patch.object(local_dungeon_flow, 'dummy_hostile', lambda run, npc: False):
            self.enter(34760, 2, 0)
            local_dungeon_flow.arena_client_end(self.run)
            self.assertFalse(self.ready())

    def test_34760_boss_room_needs_the_boss_not_the_drop_dummy(self):
        self.enter(34760, 3, 0)
        self.assertEqual(sorted(n['template'] for n in self.live()), [8286, 8412])
        self.assertEqual([n['template'] for n in self.billable()], [8286])
        self.assertFalse(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], -1)
        self.kill(self.billable()[0])
        self.assertTrue(self.ready())
        self.assertEqual(self.run.next['kind'], 4)
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(reply[0].kind, 0xb9)
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)

    def test_34760_native_expiry_rows_match_their_graph(self):
        catalog = dungeon_routes.route_catalog()
        for (identity, stage, part), row in local_dungeon_flow.NATIVE_EXPIRY_ROOMS.items():
            with self.subTest(dungeon=identity, stage=stage, part=part):
                graph = catalog.graph(identity)
                self.assertEqual(graph['source_sha256'], row['graph_sha'])
                declared = [n for group in graph['stages'][str(stage)]['parts'][str(part)]['groups']
                            for n in group['npcs']]
                for template, (script, script_sha) in row['scripts'].items():
                    native = client_data().npc(template)
                    self.assertEqual(native['script'], script)
                    self.assertIs(native['is_npc'], True)
                    self.assertEqual(catalog.manifest['source_sha256'][script], script_sha)
                    hits = [n for n in declared if n['template'] == template]
                    self.assertTrue(hits)
                    for hit in hits:
                        self.assertTrue(hit['active'])
                        self.assertFalse(hit['boss'])

    def test_34760_native_expiry_of_the_two_incubi_closes_the_room(self):
        from test_lithia_memory8_offfield_expiry import native255
        self.enter(34760, 0, 1)
        incubi = [n for n in self.live() if n['template'] == 8288
                  and n['start_point'] in (29, 31)]
        self.assertEqual(sorted(n['start_point'] for n in incubi), [29, 31])
        for npc in incubi:
            event = Event(0x202, performers=(0,), kind=0xad,
                          payload=native255(npc['key'], npc['hp'], owner=1004))
            replies = dungeon_flow.handle(self.session, event)
            self.assertEqual([r.kind for r in replies][:2], [0xae, 0xaf])
            self.assertEqual(self.run.defeated[npc['key']], event.payload)
            self.assertFalse(npc['active'])
        # The other nine declared hostiles still have to die: the fence is a
        # real room clear, not an empty roster.
        self.assertFalse(self.ready())
        self.kill_billable()
        self.assertTrue(self.ready())
        self.assertEqual((self.run.next['stage'], self.run.next['part']), (0, 2))

    def test_34760_native_expiry_is_refused_without_admission(self):
        from test_lithia_memory8_offfield_expiry import native255
        self.enter(34760, 0, 1)
        npc = next(n for n in self.live() if n['template'] == 8288
                   and n['start_point'] == 29)
        event = Event(0x202, performers=(0,), kind=0xad,
                      payload=native255(npc['key'], npc['hp'], owner=1004))
        with patch.object(local_dungeon_flow, 'native_expiry_relaxation', lambda: False):
            self.assertEqual(dungeon_flow.handle(self.session, event), [])
        self.assertEqual(self.run.defeated, {})
        self.assertTrue(npc['active'])

    def test_34760_native_expiry_requires_its_initialized_hp_and_owner(self):
        from test_lithia_memory8_offfield_expiry import native255
        self.enter(34760, 0, 1)
        npc = next(n for n in self.live() if n['template'] == 8288
                   and n['start_point'] == 29)
        wrong = Event(0x202, performers=(0,), kind=0xad,
                      payload=native255(npc['key'], npc['hp'] / 2, owner=1004))
        self.assertEqual(dungeon_flow.handle(self.session, wrong), [])
        foreign = Event(0x202, performers=(0,), kind=0xad,
                        payload=native255(npc['key'], npc['hp'], owner=1005))
        self.assertEqual(dungeon_flow.handle(self.session, foreign), [])
        self.assertEqual(self.run.defeated, {})
        self.assertTrue(npc['active'])

    def test_34760_native_expiry_replays_acknowledge_once(self):
        from test_lithia_memory8_offfield_expiry import native255
        self.enter(34760, 0, 1)
        npc = next(n for n in self.live() if n['template'] == 8288
                   and n['start_point'] == 29)
        event = Event(0x202, performers=(0,), kind=0xad,
                      payload=native255(npc['key'], npc['hp'], owner=1004))
        self.assertEqual([r.kind for r in dungeon_flow.handle(self.session, event)][:2],
                         [0xae, 0xaf])
        self.assertEqual([r.kind for r in dungeon_flow.handle(self.session, event)], [0xae])

    def test_34760_native_expiry_is_refused_outside_its_room(self):
        from test_lithia_memory8_offfield_expiry import native255
        self.enter(34760, 0, 0)
        npc = next(n for n in self.run.current['npcs'] if n['template'] == 8288)
        event = Event(0x202, performers=(0,), kind=0xad,
                      payload=native255(npc['key'], npc['hp'], owner=1004))
        self.assertEqual(dungeon_flow.handle(self.session, event), [])
        self.assertEqual(self.run.defeated, {})
        self.enter(34770, 0, 0)
        box = next(n for n in self.run.current['npcs'] if n['template'] == 8308)
        event = Event(0x202, performers=(0,), kind=0xad,
                      payload=native255(box['key'], box['hp'], owner=1004))
        self.assertEqual(dungeon_flow.handle(self.session, event), [])
        self.assertEqual(self.run.defeated, {})

    def test_34760_native_expiry_leaves_the_combat_path_alone(self):
        from els_server.domain.dungeon_lifecycle import death_report
        from test_lithia_memory8_offfield_expiry import native255
        self.enter(34760, 0, 1)
        npc = next(n for n in self.live() if n['template'] == 8288
                   and n['start_point'] == 29)
        event = Event(0x202, performers=(0,), kind=0xad,
                      payload=native255(npc['key'], npc['hp'], owner=1004))
        combat = dict(death_report(event.payload), flag=0)
        self.assertIsNone(local_dungeon_flow.native_expiry_retirement(
            self.session, event, combat))

    # -- 34770: boxing arena, branch junction, kings, final boss -----------
    def test_34770_dm_dummy_rooms_keep_their_mascots_and_boxes(self):
        for stage, part, template in ((0, 0, 8345), (3, 0, 8345)):
            with self.subTest(stage=stage, part=part):
                self.enter(34770, stage, part)
                dummy = next(n for n in self.live() if n['template'] == template)
                self.assertTrue(local_dungeon_flow.dummy_hostile(self.run, dummy))
                billable = self.billable()
                self.assertGreater(len(billable), 0)
                self.assertNotIn(template, [n['template'] for n in billable])
                self.assertFalse(self.ready())
                self.kill_billable()
                self.assertTrue(self.ready())
                self.assertIsNotNone(self.run.next)

    def test_34770_box_rooms_settle_without_the_boxes(self):
        for stage, part, target in ((0, 0, (0, 1)), (4, 1, (5, 0))):
            with self.subTest(stage=stage, part=part):
                self.enter(34770, stage, part)
                boxes = [n for n in self.live() if n['template'] == 8308]
                self.assertEqual(len(boxes), 5 if stage == 0 else 2)
                self.assertTrue(all(local_dungeon_flow.dummy_hostile(self.run, n)
                                    for n in boxes))
                self.assertEqual([n['template'] for n in self.billable() if n['template'] == 8308], [])
                self.assertFalse(self.ready())
                self.kill_billable()
                if stage == 4:
                    # stage4 part1 is kind==5: the fence also needs the
                    # client's own portal request.
                    self.assertEqual(dungeon_flow.handle(
                        self.session, portal_request(part))[0].kind, 0xb9)
                self.assertTrue(self.ready())
                self.assertEqual((self.run.next['stage'], self.run.next['part']), target)

    def test_every_themepark_dummy_row_matches_its_graph(self):
        catalog = dungeon_routes.route_catalog()
        rows = [(key, row) for key, row in local_dungeon_flow.DUMMY_HOSTILES.items()
                if key[0] in THEMEPARK]
        self.assertGreaterEqual(len(rows), 4)
        for (identity, stage, part), row in rows:
            with self.subTest(dungeon=identity, stage=stage, part=part):
                graph = catalog.graph(identity)
                self.assertEqual(graph['source_sha256'], row['graph_sha'])
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
                    hits = [n for n in declared if n['template'] == source['template']
                            and n['source_index'] == source['source_index']]
                    self.assertTrue(hits)
                    for hit in hits:
                        self.assertEqual(hit['points'], source['points'])
                        self.assertTrue(all(hit.get(k) == v for k, v in source.items()
                                            if k != 'active'))

    def test_34770_branch_room_needs_its_markers_and_the_middle_boss(self):
        self.enter(34770, 1, 0)
        self.assertEqual([n['template'] for n in self.live()], [8304])
        for template in (8335, 8336, 8337):
            marker = next(n for n in self.run.current['npcs'] if n['template'] == template)
            self.assertTrue(local_dungeon_flow.part_marker_npc(self.run, marker))
        self.assertFalse(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], -1)
        self.kill(self.billable()[0])
        self.assertTrue(self.ready())
        self.assertEqual((self.run.next['stage'], self.run.next['part']), (2, 0))
        self.assertEqual(self.run.advance(), 'stage')
        self.assertEqual((self.run.stage, self.run.part), (2, 0))

    def test_34770_king_and_queen_room_needs_both_bosses(self):
        self.enter(34770, 2, 0)
        self.assertEqual(sorted(n['template'] for n in self.billable()), [8302, 8303])
        self.assertFalse(self.ready())
        self.kill(self.billable()[0])
        self.assertFalse(self.ready())
        self.kill(self.billable()[0])
        self.assertTrue(self.ready())
        self.assertEqual((self.run.next['stage'], self.run.next['part']), (5, 0))

    def test_34770_final_room_needs_the_boss_not_the_end_marker(self):
        self.enter(34770, 5, 0)
        self.assertEqual(sorted(n['template'] for n in self.live()), [8301, 8344])
        self.assertEqual([n['template'] for n in self.billable()], [8301])
        self.assertFalse(self.ready())
        self.kill(self.billable()[0])
        self.assertTrue(self.ready())
        self.assertEqual(self.run.next['kind'], 4)

    # -- 34780: the boss hands beside the script door ----------------------
    def test_34780_boss_room_needs_the_boss_not_the_hands(self):
        self.enter(34780, 2, 0)
        self.assertEqual(sorted(n['template'] for n in self.live()), [8351, 8361, 8362])
        self.assertEqual([n['template'] for n in self.billable()], [8351])
        self.assertFalse(self.ready())
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], -1)
        self.kill(self.billable()[0])
        self.assertTrue(self.ready())
        self.assertEqual(self.run.next['kind'], 4)
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)
        # Without the pinned waiver the door's room-clear check counts the hands
        # and the part stays open forever.
        with patch.object(local_dungeon_flow, 'dummy_hostile', lambda run, npc: False):
            self.enter(34780, 2, 0)
            self.kill(self.billable()[0])
            self.assertFalse(self.ready())

    # -- 34780: the kind==5 third room settles on its own clear ------------
    def test_34780_portal_exit_row_matches_its_graph(self):
        catalog = dungeon_routes.route_catalog()
        row = local_dungeon_flow.PORTAL_EXITS[(34780, 0, 2)]
        graph = catalog.graph(34780)
        self.assertEqual(graph['source_sha256'], row['graph_sha'])
        self.assertEqual(catalog.manifest['source_sha256'][row['script']], row['script_sha'])
        condition = graph['stages']['0']['parts']['2']['conditions'][0]
        self.assertEqual((condition['kind'], condition['required'], condition['portal_lines']),
                         (5, [], [18, 19, 20, 21]))
        self.assertEqual([(t['kind'], t['stage'], t['part']) for t in condition['next']],
                         [(1, 1, 0)])

    def test_34780_third_room_settles_without_a_portal_request(self):
        self.enter(34780, 0, 2)
        self.assertEqual(len(self.live()), 7)
        self.assertTrue(local_dungeon_flow.portal_exit(self.run))
        self.assertFalse(self.run.portal_requested)
        self.assertFalse(self.ready())
        self.kill_billable()
        self.assertFalse(self.run.portal_requested)
        self.assertTrue(self.ready())
        self.assertEqual((self.run.next['stage'], self.run.next['part'], self.run.next['kind']),
                         (1, 0, 1))

    def test_34780_third_room_announces_the_part_end_once_cleared(self):
        self.enter(34780, 0, 2)
        self.assertEqual(dungeon_flow.periodic(self.session), [])
        self.kill_billable()
        self.assertEqual(dungeon_flow.periodic(self.session), [])
        self.clock.value += 200
        self.assertEqual([r.kind for r in dungeon_flow.periodic(self.session)], [0xba])

    def test_34780_third_room_stalls_without_the_waiver(self):
        self.enter(34780, 0, 2)
        self.kill_billable()
        with patch.object(local_dungeon_flow, 'portal_exit', lambda run: False):
            self.assertFalse(self.ready())

    def test_the_portal_exit_waiver_admits_only_its_own_room(self):
        # The neighbouring kind==5 room still waits for the client's request.
        self.enter(34770, 4, 1)
        self.assertEqual(self.run.current['conditions'][0]['kind'], 5)
        self.assertFalse(local_dungeon_flow.portal_exit(self.run))
        self.kill_billable()
        self.assertFalse(self.ready())
        self.run.portal_requested = True
        self.assertTrue(self.ready())
        # Nor does the pinned dungeon admit a different part.
        self.enter(34780, 0, 1)
        self.assertFalse(local_dungeon_flow.portal_exit(self.run))

    # -- 34800: lever managers and the middle boss -------------------------
    def test_34800_lever_rooms_settle_with_the_manager_alive(self):
        for stage, part, template in ((1, 0, 8399), (1, 1, 8400), (1, 2, 8401),
                                      (3, 0, 8400), (3, 1, 8401)):
            with self.subTest(stage=stage, part=part):
                self.enter(34800, stage, part)
                dummy = next(n for n in self.live() if n['template'] == template)
                self.assertTrue(local_dungeon_flow.dummy_hostile(self.run, dummy))
                billable = self.billable()
                self.assertGreater(len(billable), 0)
                self.assertFalse(self.ready())
                self.kill_billable()
                self.assertTrue(self.ready())
                self.assertIsNotNone(self.run.next)

    def test_34800_middle_boss_room_settles_on_the_boss(self):
        self.enter(34800, 2, 0)
        self.assertEqual(sorted(n['template'] for n in self.live()), [8392, 8397, 8432])
        self.assertEqual([n['template'] for n in self.billable()], [8392])
        self.assertFalse(self.ready())
        self.assertFalse(self.run.condition_ready(self.run.current['conditions'][1]))
        self.kill(self.billable()[0])
        self.assertTrue(self.ready())
        self.assertEqual((self.run.next['stage'], self.run.next['part']), (3, 0))
        reply = dungeon_flow.handle(self.session, portal_request(0))
        self.assertEqual(struct.unpack('>i', reply[0].payload)[0], 0)

    # -- 34800 stage 3: the client retires the middle-boss markers itself ---
    def marker(self, template):
        return next(n for n in self.run.current['npcs'] if n['template'] == template)

    def expiry(self, npc, **kw):
        from test_lithia_memory8_offfield_expiry import native255
        kw.setdefault('owner', 1004)
        return Event(0x202, performers=(0,), kind=0xad,
                     payload=native255(npc['key'], npc['hp'], **kw))

    def test_34800_marker_expiry_satisfies_each_source_condition(self):
        for template, target in ((8432, (3, 0)), (8397, (4, 0))):
            with self.subTest(marker=template):
                self.enter(34800, 2, 0)
                npc = self.marker(template)
                self.assertTrue(local_dungeon_flow.part_marker_npc(self.run, npc))
                replies = dungeon_flow.handle(self.session, self.expiry(npc))
                self.assertEqual([r.kind for r in replies][:2], [0xae, 0xaf])
                self.assertEqual(self.run.defeated, {npc['key']: self.expiry(npc).payload})
                self.assertFalse(npc['active'])
                self.assertEqual((self.run.next['stage'], self.run.next['part']), target)
                # 8432 has no delay, so ``periodic`` already announces the part.
                self.assertEqual([r.kind for r in replies], [0xae, 0xaf] + ([0xba] if template == 8432 else []))

    def test_34800_marker_expiry_is_admitted_only_with_its_initialized_hp(self):
        from test_lithia_memory8_offfield_expiry import native255
        self.enter(34800, 2, 0)
        npc = self.marker(8432)
        wrong = Event(0x202, performers=(0,), kind=0xad,
                      payload=native255(npc['key'], npc['hp'] / 2, owner=1004))
        self.assertEqual(dungeon_flow.handle(self.session, wrong), [])
        self.assertEqual(self.run.defeated, {})
        self.assertTrue(npc['active'])
        # A different owner is not this run's readiness entry.
        self.assertEqual(dungeon_flow.handle(self.session, self.expiry(npc, owner=1005)), [])
        self.assertEqual(self.run.defeated, {})

    def test_34800_marker_expiry_replay_acknowledges_once(self):
        self.enter(34800, 2, 0)
        npc = self.marker(8432)
        event = self.expiry(npc)
        self.assertEqual([r.kind for r in dungeon_flow.handle(self.session, event)], [0xae, 0xaf, 0xba])
        self.assertEqual([r.kind for r in dungeon_flow.handle(self.session, event)], [0xae])

    def test_34800_marker_retirement_left_the_normal_combat_path_alone(self):
        from els_server.domain.dungeon_lifecycle import death_report
        self.enter(34800, 2, 0)
        npc = self.marker(8432)
        event = self.expiry(npc)
        combat = dict(death_report(event.payload), flag=0)
        self.assertIsNone(local_dungeon_flow.part_marker_retirement(self.session, event, combat))

    def test_a_marker_expiry_is_refused_outside_the_retirement_room(self):
        self.enter(34780, 2, 0)
        npc = next(n for n in self.run.current['npcs'] if n['template'] == 8361)
        self.assertEqual(dungeon_flow.handle(self.session, self.expiry(npc)), [])
        self.assertEqual(self.run.defeated, {})
        self.assertTrue(npc['active'])

    # -- the pinned rows never leak into another row or room ---------------
    def test_a_pinned_marker_is_refused_outside_its_own_row(self):
        self.enter(34770, 1, 0)
        marker = next(n for n in self.run.current['npcs'] if n['template'] == 8335)
        self.assertTrue(local_dungeon_flow.part_marker_npc(self.run, marker))
        for forged in (dict(marker, start_point=1), dict(marker, source_index=4),
                       dict(marker, team=0)):
            self.assertFalse(local_dungeon_flow.part_marker_npc(self.run, forged))
        self.enter(34770, 2, 0)
        self.assertFalse(local_dungeon_flow.part_marker_npc(self.run, marker))

    def test_a_pinned_lever_manager_is_refused_outside_its_own_row(self):
        self.enter(34800, 1, 1)
        npc = next(n for n in self.run.current['npcs'] if n['template'] == 8400)
        self.assertTrue(local_dungeon_flow.dummy_hostile(self.run, npc))
        for forged in (dict(npc, start_point=1), dict(npc, source_index=12),
                       dict(npc, team=0), dict(npc, gage=False)):
            self.assertFalse(local_dungeon_flow.dummy_hostile(self.run, forged))
        self.run._load_stage(3)
        self.run.part = 0
        self.assertFalse(local_dungeon_flow.dummy_hostile(self.run, npc))

    # -- end to end --------------------------------------------------------
    def walk(self, identity):
        self.enter(identity, 0, 0)
        visited = []
        for _ in range(40):
            self.run.loaded()
            visited.append((self.run.stage, self.run.part))
            self.kill_billable()
            # A summon arena closes on the client's own 0xbb (arena_client_end);
            # every other portal room closes on its 0xb8.
            if local_dungeon_flow.dummy_portal(self.run):
                local_dungeon_flow.arena_client_end(self.run)
            elif not local_dungeon_flow.portal_exit(self.run) and \
                    self.run.current['conditions'][0]['kind'] == 5:
                self.run.portal_requested = True
            if not self.ready():
                self.fail('part %r never satisfies its condition' % (visited[-1],))
            if self.run.next['kind'] == 4:
                return visited, 'clear'
            self.run.advance()
        self.fail('run never settled: %r' % (visited[-1],))

    def test_34760_walks_to_a_clear(self):
        visited, verdict = self.walk(34760)
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited, [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1),
                                   (1, 2), (2, 0), (3, 0)])

    def test_34770_walks_to_a_clear(self):
        visited, verdict = self.walk(34770)
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited, [(0, 0), (0, 1), (1, 0), (2, 0), (5, 0)])

    def test_34780_walks_to_a_clear(self):
        visited, verdict = self.walk(34780)
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited, [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1),
                                   (1, 2), (1, 3), (2, 0)])

    def test_34800_walks_to_a_clear(self):
        visited, verdict = self.walk(34800)
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited, [(0, 0), (0, 1), (0, 2), (0, 3), (1, 0),
                                   (1, 1), (1, 2), (1, 3), (2, 0), (3, 0),
                                   (3, 1), (3, 2), (4, 0)])

    def test_34790_walks_to_a_clear_without_any_relaxation(self):
        with patch.object(local_dungeon_flow, 'dummy_hostile', lambda run, npc: False), \
                patch.object(local_dungeon_flow, 'dummy_portal', lambda run: False), \
                patch.object(local_dungeon_flow, 'part_marker_relaxation', lambda: False):
            visited, verdict = self.walk(34790)
        self.assertEqual(verdict, 'clear')
        self.assertEqual(visited, [(0, 0), (1, 0)])

    def test_switching_the_waivers_off_restores_the_stall(self):
        self.enter(34770, 0, 0)
        for npc in self.billable():
            self.kill(npc)
        with patch.object(local_dungeon_flow, 'dummy_hostile', lambda run, npc: False):
            self.assertFalse(self.ready())
        self.assertTrue(self.ready())

        self.enter(34800, 2, 0)
        self.kill(self.billable()[0])
        with patch.object(local_dungeon_flow, 'part_marker_relaxation', lambda: False):
            self.assertFalse(self.ready())
        self.assertTrue(self.ready())


if __name__ == '__main__':
    unittest.main()
