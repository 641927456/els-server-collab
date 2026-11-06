"""The 30282 mid-Boss death must settle on a plain local session.

Reproduction of the 纳斯德生产基地 disconnect: a solo run uses a bare
``LocalSession`` (``els_server/application.py`` only sets ``identity`` on the
friends session), while the optional bait draw snapshots ``s.identity`` in
``fishing_bait_loot._facts``. Dungeon 30282 keeps its Bosses in stage 1 / part 1
(template 193) and stage 2 / part 0 (template 261), so the first mid-Boss kill
reached that snapshot, the AttributeError escaped ``accepted_death`` before its
``LootActorRejected`` guard, and the worker dropped the connection one
millisecond after the client's 0xAD report.
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

import els_server.storage.dungeon_equipment_loot as loot_storage
from els_server.domain import dungeon_equipment_loot_flow, dungeon_flow, dungeon_routes
from els_server.domain import fishing_bait_loot
from els_server.domain.dungeon_lifecycle import death_ack
from els_server.protocol.protocol_codec import Event, encode_event

OWNER = 1004
DUNGEON = 30282


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


class MidBossDeath(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.run = dungeon_routes.DungeonRun(DUNGEON, str(uuid.uuid4()), clock=self.clock)
        self.run._load_stage(1)
        self.run.part = 1
        self.npc = next(n for n in self.run.current['npcs'] if n['boss'])
        self.event = self._event(self.npc)
        self.seen = {}
        self.refusals = []

    def _event(self, npc):
        payload = (
            struct.pack('>iBQQ6fBI', npc['key'], 0, OWNER, OWNER,
                        1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1,
                        struct.unpack('>I', struct.pack('>f', npc['hp']))[0])
            + struct.pack('>I', 1) + struct.pack('>Qf', OWNER, 1.0)
            + struct.pack('>I', 1) + struct.pack('>QB', OWNER, 1)
            + struct.pack('>Q', OWNER)
            + struct.pack('>I', 0) + struct.pack('>Q', OWNER))
        return Event(0x202, performers=(0,), kind=0xad, payload=payload)

    def session(self):
        """A plain local session: no ``identity`` and no ``application``."""
        account = NS(uid=OWNER, account_id=7, store=NS(path='x'),
                     reward_store=None, get_location=lambda: {'map': DUNGEON},
                     character=lambda: {'unit_type': 15})
        return NS(dungeon_run=self.run, account=account, role='game',
                  phase='dungeon_active', dungeon_substage_synced=True,
                  clear_notified=False, dungeon_failed=False,
                  part_end_notified=False, dungeon_clock=self.clock,
                  dungeon_participants=frozenset((OWNER,)),
                  reward_run_id=self.run.run_id, reward_transaction=None,
                  challenge_deadline=None, drop_probe=True, item_test=True,
                  reward_test=True, drop_test=True, population_test=True,
                  world_drops={}, world_drop_sequence=0, gate_stage_loading=False,
                  gate_stage=0, previous_dungeon_part=None, summon_keys=set(),
                  summon_deaths={}, summon_requests={}, summon_next_key=16,
                  defeated_npcs=self.run.defeated, application=None,
                  active_challenge=None, clear_items_synced=False,
                  active_map=DUNGEON, pending_map=None, map_synchronizing=None)

    def writer(self, *, refuse_bait=False):
        class Reached(Exception):
            pass

        def issue(path, c, proof, boss, start_id, xyz, legacy, prepare,
                  randbelow=None, rules=None, accepted_effect=None,
                  account_id=None, bait=None):
            if bait is not None and refuse_bait:
                self.refusals.append(bait)
                raise loot_storage.LootActorRejected('Bait draw already has a committed source')
            self.seen['bait'] = bait
            reply = [death_ack()]
            for event in reply:
                encode_event(event)
            return dict(reply=reply, world={}, sequence=start_id, last=None)

        return issue, Reached

    def hunter_passes(self):
        """Let the bait source construct: its own gates stop at the snapshot."""
        return (
            patch('els_server.domain.hunter_chest_flow._checked',
                  lambda *a, **k: ((), None, 'x', {'roster': []}, None)),
            patch.object(fishing_bait_loot, '_actor', lambda run, npc: {'stage': 1, 'part': 1}),
        )

    def drive(self, session, writer):
        with patch.object(loot_storage, 'issue', writer):
            return dungeon_flow.handle(session, self.event)

    def test_the_mid_boss_is_a_real_bait_route_source(self):
        self.assertEqual(self.npc['template'], 193)
        self.assertTrue(self.npc['active'])
        self.assertIn(DUNGEON, fishing_bait_loot.MAPS)

    def test_raw_identity_snapshot_reproduces_the_disconnect(self):
        # The pre-fix shape: raw s.identity in _facts, no guard at the call site.
        def raw_facts(s):
            app = getattr(s, 'application', None)
            world = getattr(app, 'world', None)
            return (id(world), id(getattr(world, 'dungeons', None)),
                    id(getattr(app, 'registry', None)), repr(s.identity),
                    s.active_map, repr(s.account.get_location()),
                    repr(getattr(s, 'pending_map', None)),
                    getattr(s, 'map_synchronizing', None))

        def unguarded(s, npc):
            return fishing_bait_loot.source(s, npc)

        writer, _ = self.writer()
        checks, actor = self.hunter_passes()
        with patch.object(fishing_bait_loot, '_facts', raw_facts), \
                patch.object(dungeon_equipment_loot_flow, '_bait', unguarded), checks, actor:
            with self.assertRaises(AttributeError):
                self.drive(self.session(), writer)

    def test_identity_less_session_settles_the_death(self):
        writer, _ = self.writer()
        reply = self.drive(self.session(), writer)
        self.assertEqual(reply, [death_ack()])
        self.assertIsNone(self.seen['bait'])

    def test_draw_is_attached_when_its_own_gates_pass(self):
        writer, _ = self.writer()
        checks, actor = self.hunter_passes()
        with checks, actor:
            reply = self.drive(self.session(), writer)
        self.assertEqual(reply, [death_ack()])
        self.assertIsInstance(self.seen['bait'], fishing_bait_loot._Source)

    def test_refused_draw_still_settles_the_death(self):
        writer, _ = self.writer(refuse_bait=True)
        with patch.object(fishing_bait_loot, 'source',
                          lambda *a, **k: NS(issue=lambda *a: [], validate=lambda *a: None)):
            reply = self.drive(self.session(), writer)
        self.assertEqual(reply, [death_ack()])
        self.assertEqual(len(self.refusals), 1)
        self.assertIsNone(self.seen['bait'])


class SourceIssueReportsRefusal(unittest.TestCase):
    def test_value_error_becomes_loot_actor_rejected(self):
        source = object.__new__(fishing_bait_loot._Source)
        source._issue = lambda *a: (_ for _ in ()).throw(ValueError('Bait ground UID bound'))
        with self.assertRaises(loot_storage.LootActorRejected):
            source.issue(None, {}, b'p', 1, [0.0], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
