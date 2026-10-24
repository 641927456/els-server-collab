"""Stage1 finale barrier: 9470 must retire before the part can end.

Trace 20261024-130855 proved the client keeps 9470's actor alive inside the
stage1/part0 scene until unload, so the part end must wait for its DYING
report; releasing the barrier on poll_ready() alone unloaded the scene before
9470 ever reported and left quest 28110 at 0/1 forever.
"""
import copy
import json
import sqlite3
import struct
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import lithia_memory1_retirements as target
from els_server.domain.lithia_memory1_retirements import GRAPH_SHA, LATER_CONTROLLERS
from els_server.protocol.protocol_codec import Event

OWNER = 1002
MAX_UID = 2**64 - 1
NPCS = [
    dict(template=9460, key=0, hp=500, active=False, start_point=1, team=1),
    dict(template=9470, key=1, hp=500, active=False, start_point=2, team=1),
    dict(template=9310, key=2, hp=1000, active=True, start_point=2, team=1),
]


class QuestStore:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE completed_quests(owner,quest)')
        self.db.execute('CREATE TABLE character_quests(owner,quest,objectives)')
        self.db.execute('INSERT INTO completed_quests VALUES (?,?)', (OWNER, 28100))
        self.db.execute('INSERT INTO character_quests VALUES (?,?,?)',
                        (OWNER, 28110, json.dumps({'28110': 0})))
        self.calls = 0
        self.witnesses = []

    def record(self, key, witness, payload, *, validate, prepare):
        self.calls += 1
        self.witnesses.append(witness)
        validate(self.db)
        return prepare([], False)


class Run(NS):
    def poll_ready(self):
        # Native graph: stage1/part0 requires 9310 (key 2) dead, then clears
        # (kind 4, delay 0). Mirror condition_ready/poll_ready faithfully.
        if self.next is None and 2 in self.defeated:
            self.next = {'kind': 4}
            self.ready_at = 0
        return self.next is not None


def session(defeated=None):
    npcs = [dict(n) for n in NPCS]
    graph = {'source_sha256': GRAPH_SHA}
    manifest = {'source_sha256': {rule['script']: rule['script_sha256']
                                  for rule in LATER_CONTROLLERS.values()}}
    catalog = NS(graph=lambda identity: graph, manifest=manifest)
    run = Run(identity=35250, run_id='memory1-stage1-test', stage=1, part=0,
              current={'npcs': npcs}, graph=graph, catalog=catalog,
              defeated=dict(defeated or {}), next=None, ready_at=None,
              memory1_quest_barrier=frozenset())
    clock = NS(total=0, started=1, pause=lambda: None, resume=lambda: None)
    return NS(dungeon_run=run,
              account=NS(uid=OWNER, character=lambda: {'unit_type': 15, 'level': 205}),
              role='game', phase='dungeon_active', dungeon_substage_synced=True,
              clear_notified=False, reward_transaction=None, reward_run_id=run.run_id,
              dungeon_participants=(OWNER,), dungeon_clock=clock,
              part_end_notified=False, defeated_npcs=run.defeated)


def report(npc):
    return dict(index=npc['key'], flag=255, status=1, source=MAX_UID, killer=MAX_UID,
                extra_uid=0, last_uid=0, contribution={}, counters={},
                readiness={OWNER: 0}, xyz=(0.,) * 6,
                hp_bits=struct.unpack('>I', struct.pack('>f', npc['hp']))[0])


def event():
    return Event(0x202, kind=0xad, performers=(0,), payload=b'native-255-fixture')


def call(s, e, r, store):
    with ExitStack() as stack:
        stack.enter_context(patch.dict(sys.modules, {
            'els_server.domain.dungeon_equipment_loot_flow': NS(current_lease=lambda actor: True),
            'els_server.domain.quest_flow': NS(store=lambda actor: store)}))
        return target.handle(s, e, r)


class Stage1FinaleBarrier(unittest.TestCase):
    def by_key(self, key):
        return next(n for n in NPCS if n['key'] == key)

    def test_dummy9470_witness_maps_to_quest_28110(self):
        store = QuestStore()
        try:
            s = session()
            self.assertEqual([x.kind for x in call(s, event(), report(self.by_key(1)), store)],
                             [0xae, 0xaf])
            self.assertEqual(store.calls, 1)
            self.assertEqual(store.witnesses[0].get('tutorial_quest'), 28110)
        finally:
            store.db.close()

    def test_story_dummy9310_cannot_end_the_part_before_9470(self):
        store = QuestStore()
        try:
            s = session()
            kinds = [x.kind for x in call(s, event(), report(self.by_key(2)), store)]
            self.assertEqual(kinds, [0xae, 0xaf])
            self.assertNotIn(0xba, kinds)
            self.assertFalse(s.part_end_notified)
            self.assertEqual(s.dungeon_run.memory1_quest_barrier, frozenset((1,)))
            self.assertEqual(set(s.dungeon_run.defeated), {2})
        finally:
            store.db.close()

    def test_full_native_order_9310_then_9470_ends_the_part(self):
        store = QuestStore()
        try:
            s = session()
            self.assertEqual([x.kind for x in call(s, event(), report(self.by_key(2)), store)],
                             [0xae, 0xaf])
            self.assertFalse(s.part_end_notified)
            kinds = [x.kind for x in call(s, event(), report(self.by_key(1)), store)]
            self.assertEqual(kinds, [0xae, 0xaf, 0xba])
            self.assertTrue(s.part_end_notified)
            self.assertEqual(set(s.dungeon_run.defeated), {1, 2})
        finally:
            store.db.close()

    def test_dummy9470_first_does_not_block_nor_end_the_part(self):
        store = QuestStore()
        try:
            s = session()
            kinds = [x.kind for x in call(s, event(), report(self.by_key(1)), store)]
            self.assertEqual(kinds, [0xae, 0xaf])
            self.assertFalse(s.part_end_notified)
            # Barrier names 9470 itself, already defeated: no effect.
            self.assertEqual(s.dungeon_run.memory1_quest_barrier, frozenset((1,)))
        finally:
            store.db.close()

    def test_replay_after_barrier_release_stays_idempotent(self):
        store = QuestStore()
        try:
            s = session()
            call(s, event(), report(self.by_key(2)), store)
            call(s, event(), report(self.by_key(1)), store)
            self.assertEqual([x.kind for x in call(s, event(), report(self.by_key(1)), store)],
                             [0xae])
            self.assertEqual(store.calls, 2)
        finally:
            store.db.close()

    def test_unearned_quest_stage_rejects_the_retirement(self):
        store = QuestStore()
        try:
            s = session(defeated={2: b'native-255-fixture'})
            store.db.execute('DELETE FROM completed_quests WHERE quest=28100')
            store.db.commit()
            self.assertEqual(call(s, event(), report(self.by_key(1)), store), [])
            self.assertNotIn(1, s.dungeon_run.defeated)
            self.assertEqual(store.calls, 1)
        finally:
            store.db.close()


if __name__ == '__main__':
    unittest.main()
