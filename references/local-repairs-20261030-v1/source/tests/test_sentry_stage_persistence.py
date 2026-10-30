"""Eve's 哨兵 (384 纳斯德侦察兵, 60 s) must survive entering the next dungeon map.

Regression: the server is the actor authority for a player summon. It spawns the
sentry with an instance key outside the stage roster (0x2D0), but a *stage*
transition answers the client's 0xBB with the cached 0xB2 population packet and
wipes ``summon_keys``/``summon_deaths``/``summon_next_key``. The client rebuilds
the scene from that packet, destroys the sentry actor 0.7-0.9 s later and reports
nothing, while the new roster re-uses the same key - so the summon vanished well
before its 60 s, and the server no longer knew it existed. Pinned against the
player's own trace ``analysis/client-6c6b5180/20261028-171135`` (five rebuild
kills, lifetimes 22.1/26.3/27.2/27.3/42.2 s).

A *part* transition (0xB7/0xBD) rebuilds nothing, so the actor survives there
and the roster is left alone.
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

from els_server.domain import dungeon_flow, dungeon_routes, summons
from els_server.domain.dungeon_npcs import MODE0_FIELDS
from els_server.protocol.protocol_codec import Event

DETECTION_TEMPLATE = 384
OWNER_UID = 1004
IDENTITY = 30302
BOSS_STAGE = 3


def sentry_request(owner_uid=OWNER_UID, template=DETECTION_TEMPLATE):
    """Encode a native-shaped 0x2CE body through one pinned layout permutation."""
    dto = bytearray(0xa4)
    struct.pack_into('<i', dto, 0, -1)          # the client never names itself
    struct.pack_into('<i', dto, 4, template)
    dto[8] = 1                                  # team
    struct.pack_into('<fff', dto, 9, 100.0, 0.0, -50.0)
    struct.pack_into('<q', dto, 0x6d, owner_uid)
    encoded = [struct.pack('>I', 1)]
    for offset, size, xor, kind in summons.LAYOUTS['0']:
        if kind == 'empty':
            encoded.append(struct.pack('>I', 3) + b'abc' if offset is None else bytes(4))
        elif size == 12:
            encoded.append(b''.join(dto[offset + i:offset + i + 4][::-1] for i in (0, 4, 8)))
        else:
            encoded.append((int.from_bytes(dto[offset:offset + size], 'little') ^ xor).to_bytes(size, 'big'))
    return b''.join(encoded)


def wire_key(payload):
    position = 4
    for offset, size, xor, kind in MODE0_FIELDS:
        if offset == 0:
            break
        position += size
    return int.from_bytes(payload[position:position + 4], 'big') ^ 0x8d0dbb13


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def pause(self):
        pass

    def resume(self):
        pass

    def seconds(self):
        return 5


class SentryStageFlow(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.run = dungeon_routes.DungeonRun(IDENTITY, str(uuid.uuid4()), clock=self.clock)
        self.session = NS(dungeon_run=self.run,
                          account=NS(uid=OWNER_UID, character=lambda: {'unit_type': 5}),
                          role='game', phase='dungeon_active', dungeon_substage_synced=True,
                          clear_notified=False, dungeon_failed=False, part_end_notified=False,
                          dungeon_clock=self.clock, dungeon_participants=frozenset((OWNER_UID,)),
                          reward_run_id=self.run.run_id, reward_transaction=None,
                          challenge_deadline=None, drop_probe=False, world_drops={},
                          world_drop_sequence=0, gate_stage_loading=False, gate_stage=0,
                          previous_dungeon_part=None, summon_keys=set(), summon_deaths={},
                          summon_requests={}, summon_next_key=16,
                          defeated_npcs=self.run.defeated, application=None,
                          active_challenge=None, clear_items_synced=False)
        self.payload = sentry_request()

    def cast(self):
        """Stand where the server has already spawned a live sentry."""
        key = max(self.run.new_npc_keys(1, set())[0], 16)
        summons.retain_sentry(self.run, key, self.payload)
        self.session.summon_keys.add(key)
        self.session.summon_next_key = key + 1
        return key

    def transition(self):
        """Clear the room, ask for the gate, and report what the flow emitted."""
        stage, part = self.run.stage, self.run.part
        for npc in list(self.run.current['npcs']):
            if npc['active'] and npc.get('team', 1) != 0:
                self.run.defeated[npc['key']] = b'\0'
        self.session.defeated_npcs = self.run.defeated
        self.run.started_at = 0.0
        self.assertTrue(self.run.poll_ready(), f'stage {stage} part {part} exit never opened')
        dungeon_flow.handle(self.session, Event(0x202, kind=0xb8, payload=struct.pack('>b', part)))
        reply = dungeon_flow.handle(self.session,
                                    Event(0x202, kind=0xbb, payload=struct.pack('>b', part)))
        return stage, self.run.stage, [event.kind for event in reply]

    def loaded(self):
        reply = dungeon_flow.handle(self.session,
                                    Event(0x202, kind=0xb3, payload=bytes(5) + struct.pack('>f', 1.0)))
        return [event.kind for event in reply], reply

    def test_stage_transition_recreates_the_live_sentry(self):
        key = self.cast()
        _, _, kinds = self.transition()
        self.assertEqual(kinds[:2], [0xbc, 0xb2])
        self.assertEqual(self.session.summon_keys, set())
        self.assertEqual(self.run.respawn_payloads, {key: self.payload})
        kinds, reply = self.loaded()
        self.assertIn(0x2d0, kinds)
        notice = next(event for event in reply if event.kind == 0x2d0)
        new_key = wire_key(notice.payload)
        self.assertNotEqual(new_key, key)
        self.assertNotIn(new_key, self.run.reserved_keys)
        self.assertGreaterEqual(new_key, 16)
        # Only the instance identity changes: the replayed actor is the same
        # owner-bound 384 the player summoned in the previous room.
        self.assertEqual(notice.payload, summons.sentry_spawn(self.payload, OWNER_UID, new_key).payload)
        self.assertEqual(self.session.summon_keys, {new_key})
        self.assertEqual(self.run.summon_payloads, {new_key: self.payload})

    def test_part_transition_leaves_the_roster_alone(self):
        self.transition()
        self.loaded()
        key = self.cast()
        before, after, kinds = self.transition()
        self.assertEqual(before, after)
        self.assertNotIn(0xb2, kinds)
        self.assertNotIn(0x2d0, kinds)
        self.assertEqual(self.run.respawn_payloads, {})
        self.assertEqual(self.session.summon_keys, {key})

    def test_expired_sentry_is_not_respawned(self):
        key = self.cast()
        self.session.summon_deaths[key] = b'\0'
        _, _, kinds = self.transition()
        self.assertEqual(kinds[:2], [0xbc, 0xb2])
        self.assertEqual(self.run.respawn_payloads, {})
        self.assertEqual(self.run.summon_payloads, {})
        loaded_kinds, _ = self.loaded()
        self.assertNotIn(0x2d0, loaded_kinds)

    def test_the_room_partners_keep_their_own_authority(self):
        self.cast()
        self.session.dungeon_participants = frozenset((OWNER_UID, 1005))
        _, _, kinds = self.transition()
        self.assertEqual(kinds[:2], [0xbc, 0xb2])
        self.assertEqual(self.run.respawn_payloads, {})
        loaded_kinds, _ = self.loaded()
        self.assertNotIn(0x2d0, loaded_kinds)

    def test_full_room_refuses_the_respawn(self):
        self.cast()
        self.transition()
        with patch('els_server.domain.dungeon_spawns.occupied_slots', lambda session: 80):
            loaded_kinds, _ = self.loaded()
        self.assertNotIn(0x2d0, loaded_kinds)
        self.assertEqual(self.session.summon_keys, set())
        self.assertEqual(self.run.respawn_payloads, {})

    def test_switch_off_restores_the_silent_loss(self):
        self.cast()
        with patch.object(summons, 'STAGE_SUMMON_PERSISTENCE_ENABLED', False):
            _, _, kinds = self.transition()
            self.assertEqual(kinds[:2], [0xbc, 0xb2])
            self.assertEqual(self.run.respawn_payloads, {})
            loaded_kinds, _ = self.loaded()
        self.assertNotIn(0x2d0, loaded_kinds)

    def test_every_later_room_gets_its_own_sentry(self):
        issued = {self.cast()}
        key = next(iter(issued))
        while self.run.stage < BOSS_STAGE:
            before, after, kinds = self.transition()
            loaded_kinds, reply = self.loaded()
            notices = [event for event in reply if event.kind == 0x2d0]
            if after == before:
                # A part transition rebuilds nothing; the actor is still there.
                self.assertEqual(notices, [])
                self.assertEqual(self.session.summon_keys, {key})
                continue
            self.assertEqual(kinds[:2], [0xbc, 0xb2])
            self.assertEqual(len(notices), 1)
            key = wire_key(notices[0].payload)
            self.assertNotIn(key, issued)
            self.assertNotIn(key, self.run.reserved_keys)
            self.assertGreaterEqual(key, 16)
            issued.add(key)
            self.assertEqual(set(self.run.summon_payloads), {key})
            self.assertEqual(self.session.summon_keys, {key})
        self.assertGreater(len(issued), 1)


class SentrySpawnRetainsRequest(unittest.TestCase):
    """The cast itself has to record the request, not only the instance key."""

    def test_retain_and_carry_use_the_run_registries(self):
        run = NS(summon_payloads={}, respawn_payloads={})
        session = NS(dungeon_run=run, account=NS(uid=OWNER_UID),
                     dungeon_participants=frozenset((OWNER_UID,)),
                     summon_keys={19}, summon_deaths={})
        payload = sentry_request()
        summons.retain_sentry(run, 19, payload)
        self.assertEqual(run.summon_payloads, {19: payload})
        summons.carry_summons(session)
        self.assertEqual(run.respawn_payloads, {19: payload})
        self.assertEqual(run.summon_payloads, {})
        summons.retain_sentry(None, 19, payload)

    def test_local_session_records_the_cast(self):
        import tempfile
        from els_server.domain.local_session import LocalAccount, LocalSession
        from els_server.storage.local_state import LocalState
        with tempfile.TemporaryDirectory() as tmp:
            root = LocalAccount(LocalState(Path(tmp) / 'save.db'))
            root.enable_characters()
            eve = root.characters.create('EveTest', 5, 'create')
            self.request = sentry_request(owner_uid=eve['uid'])
            session = LocalSession(root.for_character(eve['uid']), enter_town=True, enter_dungeon=True,
                                   client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                                   population_test=True)
            session.role = 'game'
            session.phase = 'dungeon_active'
            session.dungeon_substage_synced = True
            run = dungeon_routes.DungeonRun(IDENTITY, str(uuid.uuid4()), clock=FakeClock())
            session.dungeon_run = run
            session.defeated_npcs = run.defeated
            reply = session.handle(Event(0x202, kind=0x2ce, payload=self.request), 50)
            self.assertEqual([event.kind for event in reply], [0x2cf, 0x2d0])
            key = wire_key(reply[1].payload)
            self.assertEqual(run.summon_payloads, {key: self.request})
            self.assertEqual(session.summon_keys, {key})
            # The key the server handed out is never one of the room's actors.
            self.assertNotIn(key, run.reserved_keys)
            # A replay of the same sequence does not duplicate the retention.
            session.handle(Event(0x202, kind=0x2ce, payload=self.request), 50)
            self.assertEqual(run.summon_payloads, {key: self.request})

    def setUp(self):
        self.request = sentry_request()


if __name__ == '__main__':
    unittest.main(verbosity=2)
