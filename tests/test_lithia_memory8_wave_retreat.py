"""35320 stage3 part0: the room's own 9432 wave is what opens the last door.

Session 20261025-203712, run in the boss room from 12:44:01Z: key 0 (9431,
LITHIA_MEMORY8_STORY_BOSS) went 5000 -> 0 -> 2995 inside one second and then
walked away, the client showed 「右边的大门打开了」, and nothing else happened.
The room declares one condition, kind 3 required [9452]: a 1000 HP story dummy
that stayed at full HP until the run was abandoned at 12:47:12. The client never
reported it and never sent 0xb8/0xbb (last ones 12:43:57-12:44:00, in the
previous room), so the server never emitted 0xba and the door stayed shut.

The boss's own exit is performed locally by the client and is never reported.
The room's 8 accepted 0xad deaths are all its own dynamic 9432 wave, requested
through one 0x2ce (recorded rows carry flag 0x4e = 0, so they are not active
room actors): 20261025-203712 destroys each corpse ~3.88s after its report, and
20261025-212603 shows the same 8-member wave dying 13:32:04-25 while 9452 stays
at 1000. The last accepted death of that wave retires the room's sentinel. The
sentinel is not defeated: quest 28590's kill objective still needs its own proof.

The retreat only produces the gate notice (0xba) that makes the client show
「右边的大门打开了」 and ask for the part (0xbb). That request must not end the
run: the ending comes from the sentinel's own source retirement, which happens
after the fight the opened gate leads to.
"""
import struct
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import dungeon_flow
from els_server.domain.dungeon_routes import DungeonRun
from els_server.protocol.protocol_codec import Event

OWNER = 1001
DUNGEON = 35320
BOSS, BOSS_KEY, BOSS_HP = 9431, 0, 5000
SENTINEL, SENTINEL_KEY = 9452, 4
TRASH, TRASH_KEY = 9437, 1
WAVE, WAVE_KEYS, WAVE_HP = 9432, tuple(range(14, 22)), 500


def credited(key, hp):
    return (struct.pack('>iBQQ6fBI', key, 1, OWNER, OWNER, 0, 0, 0, 0, 0, 0, 1,
                        struct.unpack('>I', struct.pack('>f', float(hp)))[0])
            + struct.pack('>I', 1) + struct.pack('>Qf', OWNER, float(hp))
            + struct.pack('>I', 1) + struct.pack('>QB', OWNER, 0)
            + struct.pack('>Q', 0)
            + struct.pack('>I', 1) + struct.pack('>Qi', OWNER, 1)
            + struct.pack('>Q', OWNER))


def run_stage(stage, part, dungeon=DUNGEON):
    run = DungeonRun(dungeon, '00000000-0000-4000-8000-000000000001')
    run._load_stage(stage)
    run.part = part
    run.loaded()
    return run


def spawn_wave(run, keys=WAVE_KEYS, template=WAVE):
    for key in keys:
        run.current['npcs'].append(dict(key=key, template=template, key_code=key, active=False,
                                        team=1, ally=False, no_drop=True, boss=False, hp=WAVE_HP,
                                        dynamic=True, wire=b'', init=b''))


def session(run, *, part_end_notified=False):
    return NS(dungeon_run=run, account=NS(uid=OWNER, character=lambda: {'unit_type': 15, 'level': 93}),
              role='game', phase='dungeon_active', dungeon_substage_synced=True,
              clear_notified=False, part_end_notified=part_end_notified, gate_stage_loading=False,
              dungeon_participants=frozenset((OWNER,)), reward_run_id=run.run_id, reward_transaction=None,
              reward_test=False, item_test=False, drop_probe=False, reward_probe=0, summon_keys=set(),
              defeated_npcs=run.defeated, world_drops={}, world_drop_sequence=0,
              dungeon_clock=NS(pause=lambda: None, resume=lambda: None))


def death(s, key, hp):
    return dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad, payload=credited(key, hp)))


def actor(run, key):
    return next(n for n in run.current['npcs'] if n['key'] == key)


class BossRoomSource(unittest.TestCase):
    def test_the_room_waits_on_a_sentinel_the_boss_is_not_part_of(self):
        run = run_stage(3, 0)
        boss, sentinel = actor(run, BOSS_KEY), actor(run, SENTINEL_KEY)
        self.assertEqual((boss['template'], boss['hp'], boss['boss']), (BOSS, BOSS_HP, True))
        self.assertEqual((sentinel['template'], sentinel['hp']), (SENTINEL, 1000))
        self.assertEqual(len(run.current['conditions']), 1)
        condition = run.current['conditions'][0]
        self.assertEqual((condition['kind'], condition['required']), (3, [SENTINEL]))
        self.assertEqual(condition['next'][0]['kind'], 4)
        self.assertFalse(run.condition_ready(condition))


class WaveRetreat(unittest.TestCase):
    def test_every_lithia_memory8_route_end_retires_its_sentinel(self):
        for dungeon, (stage, part) in ((35320, (3, 0)), (35321, (2, 0)), (35322, (0, 0))):
            run = run_stage(stage, part, dungeon)
            spawn_wave(run)
            run.defeated.update({k: b'' for k in WAVE_KEYS})
            self.assertEqual(dungeon_flow.wave_retreat(run, actor(run, WAVE_KEYS[-1])), (SENTINEL,), dungeon)
            self.assertEqual(dungeon_flow.wave_retreat(run, actor(run, BOSS_KEY)), (), dungeon)

    def test_a_route_end_does_not_answer_another_route(self):
        # The rule is pinned to each route's own source hash and stage/part, so a
        # wave in 35320's own earlier rooms never names the final room's sentinel.
        early = run_stage(0, 0)
        spawn_wave(early)
        early.defeated.update({k: b'' for k in WAVE_KEYS})
        self.assertEqual(dungeon_flow.wave_retreat(early, actor(early, WAVE_KEYS[-1])), ())

    def test_the_last_wave_death_opens_the_35322_door(self):
        run = run_stage(0, 0, 35322)
        spawn_wave(run)
        s = session(run)
        for key in WAVE_KEYS[:-1]:
            self.assertEqual([e.kind for e in death(s, key, WAVE_HP)], [0xae, 0xaf])
        self.assertFalse(s.part_end_notified)
        self.assertEqual([e.kind for e in death(s, WAVE_KEYS[-1], WAVE_HP)], [0xae, 0xaf, 0xba])
        self.assertEqual(run.retreated, {SENTINEL_KEY})

    def test_the_last_wave_death_opens_the_door(self):
        run = run_stage(3, 0)
        spawn_wave(run)
        s = session(run)
        for key in WAVE_KEYS[:-1]:
            self.assertEqual([e.kind for e in death(s, key, WAVE_HP)], [0xae, 0xaf])
        self.assertFalse(s.part_end_notified)
        self.assertEqual(run.retreated, set())
        reply = death(s, WAVE_KEYS[-1], WAVE_HP)
        self.assertEqual([e.kind for e in reply], [0xae, 0xaf, 0xba])
        self.assertTrue(s.part_end_notified)
        self.assertTrue(run.condition_ready(run.current['conditions'][0]))
        self.assertEqual(run.retreated, {SENTINEL_KEY})
        # Retreated is not defeated: 28590's kill objective still needs its proof.
        self.assertEqual(set(run.defeated), set(WAVE_KEYS))
        self.assertNotIn(SENTINEL_KEY, run.defeated)
        self.assertFalse(s.clear_notified)
        self.assertIsNone(getattr(s, 'world_drop_issued', None))

    def test_the_gate_notice_does_not_end_the_run(self):
        run = run_stage(3, 0)
        spawn_wave(run)
        s = session(run)
        for key in WAVE_KEYS:
            death(s, key, WAVE_HP)
        with patch('els_server.domain.dungeon_flow.clear', return_value=[Event(0x201, kind=0xc1, payload=bytes(4))]) as cleared:
            reply = dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xbb,
                                                 payload=struct.pack('>b', run.part)))
        self.assertEqual([e.kind for e in reply], [0xbc])
        cleared.assert_not_called()
        self.assertFalse(s.clear_notified)
        self.assertIsNone(run.completed_transition)
        self.assertEqual(run.stage, 3)
        self.assertEqual(run.next['kind'], 4)
        # The sentinel that names the ending is still on the field; only the
        # wave pushed it out, so the gate's fight has not happened yet.
        self.assertNotIn(SENTINEL_KEY, run.defeated)
        self.assertIn(SENTINEL_KEY, run.retreated)
        self.assertTrue(run.condition_ready(run.current['conditions'][0]))

    def test_the_sentinel_retirement_ends_the_run(self):
        run = run_stage(3, 0)
        spawn_wave(run)
        s = session(run)
        for key in WAVE_KEYS:
            death(s, key, WAVE_HP)
        dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xbb,
                                     payload=struct.pack('>b', run.part)))
        # Its source script retires it after the fight behind the opened gate.
        run.defeated[SENTINEL_KEY] = b''
        with patch('els_server.domain.dungeon_flow.clear', return_value=[Event(0x201, kind=0xc1, payload=bytes(4))]) as cleared:
            reply = dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xbb,
                                                 payload=struct.pack('>b', run.part)))
        self.assertEqual([e.kind for e in reply], [0xbc, 0xc1])
        cleared.assert_called_once_with(s)
        self.assertEqual(run.completed_transition['target'], (3, 0, run.visits))

    def test_the_boss_exit_alone_does_not_open_the_door(self):
        # The client performs this exit locally and never reports 9452 either.
        run = run_stage(3, 0)
        spawn_wave(run)
        s = session(run)
        self.assertEqual([e.kind for e in death(s, BOSS_KEY, BOSS_HP)], [0xae, 0xaf])
        self.assertEqual([e.kind for e in death(s, TRASH_KEY, 500)], [0xae, 0xaf])
        self.assertFalse(s.part_end_notified)
        self.assertEqual(run.retreated, set())
        self.assertEqual(dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xbb,
                                                      payload=struct.pack('>b', run.part))), [])

    def test_the_door_stays_shut_while_one_wave_member_lives(self):
        run = run_stage(3, 0)
        spawn_wave(run, keys=WAVE_KEYS[:2])
        s = session(run)
        death(s, WAVE_KEYS[0], WAVE_HP)
        self.assertFalse(s.part_end_notified)
        self.assertEqual(run.retreated, set())

    def test_a_wave_death_is_still_admitted_once(self):
        run = run_stage(3, 0)
        spawn_wave(run)
        s = session(run)
        payload = credited(WAVE_KEYS[0], WAVE_HP)
        dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad, payload=payload))
        replay = dungeon_flow.handle(s, Event(0x202, performers=(0,), kind=0xad, payload=payload))
        self.assertEqual([e.kind for e in replay], [0xae])
        self.assertEqual(set(run.defeated), {WAVE_KEYS[0]})
        self.assertEqual(run.retreated, set())


if __name__ == '__main__':
    unittest.main()
