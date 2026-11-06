"""Master Road Rosso (34390) only retires its own five declared controllers."""
import struct
import sys
import unittest
import uuid
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import dungeon_flow
from els_server.domain import dungeon_routes
from els_server.domain import master_road_rosso_retirements as rosso
from els_server.domain.dungeon_lifecycle import death_report
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event

OWNER = 1002
MAX_UID = 2**64 - 1
GRAPH_SHA = '8da85dcaca627f50d6a5bbacfa06507929f8e358a5be630e02b0f8577869642d'


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.total = 0.0
        self.started = None

    def __call__(self):
        return self.value

    def pause(self):
        self.started = None

    def resume(self):
        self.started = self.value


def native255(index, hp, owner=OWNER, xyz=(0.0,) * 6):
    """Original 16E1760 source retirement: sentinel identity, one zero readiness."""
    return (struct.pack('>iBQQ6fBI', index, 255, MAX_UID, MAX_UID, *xyz, 1,
                        struct.unpack('>I', struct.pack('>f', float(hp)))[0])
            + struct.pack('>I', 0) + struct.pack('>IQB', 1, owner, 0) + struct.pack('>Q', 0)
            + struct.pack('>I', 0) + struct.pack('>Q', 0))


def fixture(stage=0, part=0, unit=15, identity=34390):
    clock = FakeClock()
    run = dungeon_routes.DungeonRun(identity, str(uuid.uuid4()), clock=clock)
    if stage or part:
        run.stage = stage
        run._load_stage(stage)
        run.part = part
    run.loaded()
    session = NS(dungeon_run=run, account=NS(uid=OWNER, character=lambda: {'unit_type': unit}),
                 role='game', phase='dungeon_active', dungeon_substage_synced=True,
                 clear_notified=False, part_end_notified=False, dungeon_clock=clock,
                 dungeon_participants=frozenset((OWNER,)), reward_run_id=run.run_id,
                 reward_transaction=None, summon_keys=set(), defeated_npcs=run.defeated,
                 challenge_deadline=None, application=None, drop_probe=False,
                 world_drops={}, world_drop_sequence=0, gate_stage_loading=False,
                 gate_stage=0, previous_dungeon_part=None, summon_deaths={},
                 summon_requests={}, summon_next_key=16)
    return session, run, clock


def call(s, event):
    with patch.dict(sys.modules, {
            'els_server.domain.hunter_chest_flow': NS(accepted_death=lambda *a: None,
                                                     solo_loaded=lambda *a: []),
            'els_server.domain.lithia_memory1_retirements': NS(handle=lambda *a: None),
            'els_server.domain.scene_actor_retirements': NS(handle=lambda *a: None),
            'els_server.domain.devildom1_raid2_controllers': NS(handle=lambda *a: None),
            'els_server.domain.story_controller_retirements': NS(handle=lambda *a: None,
                                                                gate_predecessor_blocked=lambda *a: False),
            'els_server.domain.dungeon_equipment_loot_flow': NS(accepted_death=lambda *a: None,
                                                               current_lease=lambda *a: True),
            'els_server.domain.pve_economy_flow': NS(prepared_death=lambda *a: None),
            'els_server.domain.raid_economy_flow': NS(managed=lambda *a: False, solo=lambda *a: None),
            'els_server.domain.legacy_pve_exp': NS(accepted_death=lambda *a: None)}):
        return dungeon_flow.handle(s, event)


def retire(index, hp=30000.0, owner=OWNER, xyz=(0.0,) * 6):
    return Event(0x202, performers=(0,), kind=0xad, payload=native255(index, hp, owner, xyz))


def kill(index, hp, owner=OWNER):
    """Player-attributed death: flag 0 with the owner in every map."""
    return Event(0x202, performers=(0,), kind=0xad, payload=(
        struct.pack('>iBQQ6fBI', index, 0, owner, owner, 0, 0, 0, 0, 0, 0, 1,
                    struct.unpack('>I', struct.pack('>f', float(hp)))[0])
        + struct.pack('>I', 0) + struct.pack('>IQB', 1, owner, 0) + struct.pack('>Q', 0)
        + struct.pack('>I', 0) + struct.pack('>Q', owner)))


class RossoSources(unittest.TestCase):
    def test_every_declared_actor_is_pinned(self):
        session, run, _ = fixture()
        self.assertEqual(run.graph['source_sha256'], GRAPH_SHA)
        self.assertEqual([(n['key'], n['template']) for n in run.current['npcs']],
                         [(0, 7800), (1, 7801), (2, 7802), (3, 7803), (4, 7804)])
        for npc in run.current['npcs']:
            rule = rosso.source_rule(run, npc)
            self.assertIsNotNone(rule, npc['key'])
            source = rosso.SOURCES[npc['key']]
            self.assertEqual(rule['source']['template'], source['template'])
            native = client_data().npc(source['template'])
            self.assertEqual(native['script'], source['script'])
            self.assertEqual(native['class_id'], source['class_id'])
            self.assertIs(native['is_npc'], True)
            self.assertEqual(rule['hp'], npc['hp'])

    def test_room_condition_names_the_drop_wrapper(self):
        session, run, _ = fixture()
        conditions = run.current['conditions']
        self.assertEqual([(c['kind'], tuple(c['required']), c['next'][0]['kind'])
                          for c in conditions], [(3, (7803,), 4)])
        drop = next(n for n in run.current['npcs'] if n['template'] == 7803)
        self.assertIs(drop['active'], False)
        self.assertIs(drop['no_drop'], False)

    def test_boss_row_is_the_active_gauge_boss(self):
        session, run, _ = fixture()
        rule = rosso.source_rule(run, run.current['npcs'][0])
        self.assertEqual(rule['source']['boss'], True)
        self.assertEqual(rule['source']['active'], True)
        self.assertEqual(rule['hp'], run.current['npcs'][0]['hp'])


# Hell rooms share the shape: eight declared rows, boss at key 0, the kind-3
# exit naming the DROP1 wrapper at key 3.
HELL = {
    34400: {'graph': 'd7dadf378781f4872d6f62bb09adfa4d2a0e7b43b3cbbf67c09e93936767e110',
            'templates': [7807, 7808, 7809, 7810, 7811, 7812, 7815, 7813]},
    34420: {'graph': '93ac0876a5ad462005f157c1c833f7ac8a9920d30cfb869aca8eef1be2210e4b',
            'templates': [7650, 7653, 7654, 7655, 7656, 7657, 7659, 7658]},
}


class RossoHellSources(unittest.TestCase):
    def test_every_declared_actor_is_pinned(self):
        for identity, spec in HELL.items():
            with self.subTest(identity=identity):
                _, run, _ = fixture(identity=identity)
                self.assertEqual(run.graph['source_sha256'], spec['graph'])
                self.assertEqual([n['template'] for n in run.current['npcs']], spec['templates'])
                for npc in run.current['npcs']:
                    rule = rosso.source_rule(run, npc)
                    self.assertIsNotNone(rule, npc['key'])
                    source = rosso.ROOMS[identity]['sources'][npc['key']]
                    self.assertEqual(rule['source']['template'], source['template'])
                    native = client_data().npc(source['template'])
                    self.assertEqual(native['script'], source['script'])
                    self.assertEqual(native['class_id'], source['class_id'])
                    self.assertIs(native['is_npc'], True)
                    self.assertEqual(rule['hp'], npc['hp'])

    def test_room_condition_names_the_drop_wrapper(self):
        for identity, spec in HELL.items():
            with self.subTest(identity=identity):
                _, run, _ = fixture(identity=identity)
                self.assertEqual([(c['kind'], tuple(c['required']), c['next'][0]['kind'])
                                  for c in run.current['conditions']],
                                 [(3, (spec['templates'][3],), 4)])
                drop = run.current['npcs'][3]
                self.assertIs(drop['active'], False)
                self.assertIs(drop['no_drop'], False)

    def test_boss_row_is_the_active_gauge_boss(self):
        for identity in HELL:
            with self.subTest(identity=identity):
                _, run, _ = fixture(identity=identity)
                rule = rosso.source_rule(run, run.current['npcs'][0])
                self.assertEqual(rule['source']['boss'], True)
                self.assertEqual(rule['source']['active'], True)

    def test_boss_and_drop_wrapper_unstick_the_part(self):
        for identity in HELL:
            with self.subTest(identity=identity):
                session, run, _ = fixture(identity=identity)
                boss_hp = run.current['npcs'][0]['hp']
                self.assertEqual([r.kind for r in call(session, retire(0, boss_hp))],
                                 [0xae, 0xaf])
                self.assertFalse(session.part_end_notified)
                self.assertEqual([r.kind for r in call(session, retire(3, 119702.1015625))],
                                 [0xae, 0xaf, 0xba])
                self.assertTrue(session.part_end_notified)
                self.assertEqual(run.next['kind'], 4)
                gate = call(session, Event(0x202, performers=(0,), kind=0xb8, payload=b'\0'))
                self.assertEqual([r.kind for r in gate], [0xb9])
                cleared = []

                def fake_clear(s):
                    cleared.append((s.dungeon_run.stage, s.dungeon_run.part))
                    return [Event(0x201, kind=0xc1, payload=bytes(4))]

                with patch.object(dungeon_flow, 'clear', fake_clear):
                    reply = call(session, Event(0x202, performers=(0,), kind=0xbb, payload=b'\0'))
                self.assertEqual([r.kind for r in reply], [0xbc, 0xc1])
                self.assertEqual(cleared, [(0, 0)])


class RossoRetirements(unittest.TestCase):
    def test_boss_and_drop_wrapper_unstick_the_part(self):
        session, run, clock = fixture()
        self.assertEqual([r.kind for r in call(session, retire(0, run.current['npcs'][0]['hp']))],
                         [0xae, 0xaf])
        self.assertIn(0, run.defeated)
        # The spawn flag is left alone, as on the ordinary combat path.
        self.assertIs(run.current['npcs'][0]['active'], True)
        self.assertFalse(session.part_end_notified)
        self.assertEqual([r.kind for r in call(session, retire(3, 119702.1015625))],
                         [0xae, 0xaf, 0xba])
        self.assertTrue(session.part_end_notified)
        self.assertEqual(run.next['kind'], 4)
        gate = call(session, Event(0x202, performers=(0,), kind=0xb8, payload=b'\0'))
        self.assertEqual([r.kind for r in gate], [0xb9])
        self.assertEqual(struct.unpack('>i', gate[0].payload)[0], 0)
        cleared = []

        def fake_clear(s):
            cleared.append((s.dungeon_run.stage, s.dungeon_run.part))
            return [Event(0x201, kind=0xc1, payload=bytes(4))]

        with patch.object(dungeon_flow, 'clear', fake_clear):
            reply = call(session, Event(0x202, performers=(0,), kind=0xbb, payload=b'\0'))
        self.assertEqual([r.kind for r in reply], [0xbc, 0xc1])
        self.assertEqual(cleared, [(0, 0)])

    def test_all_five_reports_are_admitted(self):
        session, run, _ = fixture()
        for key in range(5):
            hp = run.current['npcs'][key]['hp']
            self.assertEqual([r.kind for r in call(session, retire(key, hp))][:2], [0xae, 0xaf], key)
            self.assertIn(key, run.defeated)
        self.assertTrue(session.part_end_notified)

    def test_dying_gauge_floor_is_the_observed_report(self):
        # The client clamps the dying boss to max/1000 (20261030-153805).
        session, run, _ = fixture()
        self.assertEqual([r.kind for r in call(session, retire(0, run.current['npcs'][0]['hp'] / 1000))],
                         [0xae, 0xaf])
        self.assertIn(0, run.defeated)

    def test_hp_outside_the_initialized_maximum_is_rejected(self):
        _, probe, _ = fixture()
        maximum = probe.current['npcs'][0]['hp']
        for hp in (0.0, maximum * 2.0, float('nan')):
            session, run, _ = fixture()
            self.assertEqual(call(session, retire(0, hp)), [], hp)
            self.assertEqual(run.defeated, {}, hp)

    def test_retirement_is_idempotent_and_byte_exact(self):
        session, run, _ = fixture()
        event = retire(3, 119702.1015625)
        self.assertEqual([r.kind for r in call(session, event)][:2], [0xae, 0xaf])
        self.assertEqual([r.kind for r in call(session, event)], [0xae])
        self.assertEqual(run.defeated, {3: event.payload})
        self.assertEqual(call(session, retire(3, 119702.1015625,
                                              xyz=(1.0, 1.0, 1.0, 1.0, 1.0, 1.0))), [])
        self.assertEqual(run.defeated, {3: event.payload})

    def test_plain_kill_flag_is_left_to_the_generic_path(self):
        session, run, _ = fixture()
        payload = bytearray(native255(0, run.current['npcs'][0]['hp']))
        struct.pack_into('>B', payload, 4, 0)
        report = death_report(bytes(payload))
        self.assertIsNone(rosso.handle(session, Event(0x202, performers=(0,),
                                                      kind=0xad, payload=bytes(payload)), report))
        self.assertEqual(run.defeated, {})

    def test_foreign_owner_or_participant_is_rejected(self):
        session, run, _ = fixture()
        self.assertEqual(call(session, retire(3, 119702.1015625, owner=OWNER + 1)), [])
        session.dungeon_participants = frozenset((OWNER, OWNER + 1))
        self.assertEqual(call(session, retire(3, 119702.1015625)), [])
        self.assertEqual(run.defeated, {})

    def test_other_room_or_undeclared_index_is_not_admitted(self):
        session, run, _ = fixture()
        session.dungeon_run.identity = 34391
        self.assertIsNone(rosso.handle(session, retire(3, 119702.1015625), {
            'flag': 255, 'index': 3, 'hp_bits': struct.unpack('>I', struct.pack('>f', 119702.1015625))[0],
            'status': 1, 'source': MAX_UID, 'killer': MAX_UID, 'last_uid': 0, 'extra_uid': 0,
            'contribution': {}, 'counters': {}, 'readiness': {OWNER: 0}, 'xyz': (0.0,) * 6}))
        session2, run2, _ = fixture()
        self.assertIsNone(rosso.handle(session2, retire(7, 30000.0), {
            'flag': 255, 'index': 7, 'hp_bits': struct.unpack('>I', struct.pack('>f', 30000.0))[0],
            'status': 1, 'source': MAX_UID, 'killer': MAX_UID, 'last_uid': 0, 'extra_uid': 0,
            'contribution': {}, 'counters': {}, 'readiness': {OWNER: 0}, 'xyz': (0.0,) * 6}))
        self.assertEqual(run2.defeated, {})

    def test_retirement_is_not_committed_when_encoding_fails(self):
        session, run, _ = fixture()
        with patch('els_server.protocol.protocol_codec.encode_event',
                   side_effect=RuntimeError('encode must fail first')) as encoded:
            with self.assertRaises(RuntimeError):
                call(session, retire(3, 119702.1015625))
            encoded.assert_called()
        self.assertEqual(run.defeated, {})
        self.assertFalse(session.part_end_notified)

    def test_toggle_only_disables_the_new_admission(self):
        session, run, _ = fixture()
        with patch.object(rosso, 'MASTER_ROAD_RETIREMENTS_ENABLED', False):
            self.assertEqual(rosso.handle(session, retire(3, 119702.1015625), {
                'flag': 255, 'index': 3,
                'hp_bits': struct.unpack('>I', struct.pack('>f', 119702.1015625))[0],
                'status': 1, 'source': MAX_UID, 'killer': MAX_UID, 'last_uid': 0,
                'extra_uid': 0, 'contribution': {}, 'counters': {},
                'readiness': {OWNER: 0}, 'xyz': (0.0,) * 6}), None)


if __name__ == '__main__':
    unittest.main()
