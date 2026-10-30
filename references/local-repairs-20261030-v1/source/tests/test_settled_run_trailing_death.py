"""A settled run must survive the death reports the client sends after BB.

Regression for the clear-panel crash: the client emits the deaths that landed
in the same frame as its BB, so one 0xAD arrives after the clear packets. That
report used to reach legacy_population, whose C1 guard refuses a post-clear
lease by raising SessionOrderError, tearing down the connection.
"""
import struct
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import dungeon_flow, dungeon_routes
from els_server.domain.dungeon_lifecycle import death_ack
from els_server.protocol.protocol_codec import Event

OWNER = 1002
IDENTITY = 30000


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

    def seconds(self):
        return 5


class RecordingHP:
    """Stand-in for the C1 HP context; records whether it was consulted."""

    def __init__(self):
        self.checked = 0

    def bind_run(self, run):
        pass

    def check(self, run=None, *, emitting=False):
        self.checked += 1
        raise AssertionError('settled run must not consult the C1 HP context')

    def source_hp(self, run, stage, part, group, source, fallback):
        return fallback


def kill(index=0, hp=1000.0, owner=OWNER):
    return Event(0x202, performers=(0,), kind=0xad, payload=(
        struct.pack('>iBQQ6fBI', index, 0, owner, owner, 0, 0, 0, 0, 0, 0, 1,
                    struct.unpack('>I', struct.pack('>f', float(hp)))[0])
        + struct.pack('>I', 0) + struct.pack('>IQB', 1, owner, 0) + struct.pack('>Q', 0)
        + struct.pack('>I', 0) + struct.pack('>Q', owner)))


def fixture(*, cleared=False, failed=False, hp=None):
    clock = FakeClock()
    run = dungeon_routes.DungeonRun(IDENTITY, '00000000-0000-0000-0000-000000030000',
                                    clock=clock, hp_context=hp)
    run.loaded()
    s = NS(dungeon_run=run, account=NS(uid=OWNER, character=lambda: {'unit_type': 15}),
           role='game', phase='dungeon_active', dungeon_substage_synced=True,
           clear_notified=cleared, dungeon_failed=failed, part_end_notified=False,
           dungeon_clock=clock, dungeon_participants=frozenset((OWNER,)),
           reward_run_id=run.run_id, reward_transaction=None, challenge_deadline=None,
           drop_probe=False, world_drops={}, world_drop_sequence=0,
           gate_stage_loading=False, gate_stage=0, previous_dungeon_part=None,
           summon_keys=set(), summon_deaths={}, summon_requests={}, summon_next_key=16,
           defeated_npcs=run.defeated, application=None, item_test=True, reward_test=True,
           active_challenge=None, clear_items_synced=False)
    return s, run


def call(s, event):
    with patch.dict(sys.modules, {
            'els_server.domain.hunter_chest_flow': NS(accepted_death=lambda *a: None,
                                                     solo_loaded=lambda *a: [])}):
        return dungeon_flow.handle(s, event)


class SettledRunTrailingDeath(unittest.TestCase):
    def test_clear_acknowledges_and_drops_a_trailing_death(self):
        hp = RecordingHP()
        s, run = fixture(cleared=True, hp=hp)
        self.assertEqual(call(s, kill()), [death_ack()])
        self.assertEqual(hp.checked, 0)
        self.assertEqual(run.defeated, {})

    def test_failed_run_does_the_same(self):
        hp = RecordingHP()
        s, run = fixture(failed=True, hp=hp)
        self.assertEqual(call(s, kill()), [death_ack()])
        self.assertEqual(hp.checked, 0)

    def test_live_run_still_falls_through_the_guard(self):
        # An unsettled run must reach the ordinary consumers, not the guard.
        s, run = fixture()
        with patch.dict(sys.modules, {
                'els_server.domain.hunter_chest_flow': NS(
                    accepted_death=lambda *a: 'HUNTER', solo_loaded=lambda *a: [])}):
            self.assertEqual(dungeon_flow.handle(s, kill()), 'HUNTER')

    def test_guard_is_per_run_not_per_connection(self):
        # Entering a fresh run resets the flags, so the guard cannot latch on.
        s, run = fixture(cleared=True)
        self.assertEqual(call(s, kill()), [death_ack()])
        s.clear_notified = False
        s.dungeon_failed = False
        with patch.dict(sys.modules, {
                'els_server.domain.hunter_chest_flow': NS(
                    accepted_death=lambda *a: 'HUNTER', solo_loaded=lambda *a: [])}):
            self.assertEqual(dungeon_flow.handle(s, kill()), 'HUNTER')


if __name__ == '__main__':
    unittest.main()
