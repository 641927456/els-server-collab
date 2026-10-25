"""LITHIA_MEMORY5 (35290) controllers retire on the client's scene timeline.

Server log 20261025-144602: stage 0 part 1 finished its seven thieves and the
chest (keys 8-14 acknowledged), then the client reported wire key 7 = template
9377 (LITHIA_MEMORY5_SUMMON2.lua) once at 06:53:46 and never again. 90 of 91
reports were acknowledged; key 7 alone kept its actor at full 1000 HP in every
frame until the player left 203 s later. The pinned graph makes retiring 9377
the part clear condition (kind 3, required [9377], graph sha
dd9c58d5250519dfa1a4d1bec1893619c304f0e02effb12a672feb092416ab15), so the
unacknowledged report left the blue gate shut for the rest of the run.

The report was refused by the quest-stage precondition, not by identity: the
rule names epic quest 28380, and the chain accepts 28380 only after 28370 is
earned, which needs this dungeon cleared first. The same holds for 28390/28400/
28410. Following the merged 35270 relaxation, a quest that cannot be active yet
must not strand the scene; quest credit still needs an active matching quest, so
accepting these retirements grants no progress.
"""
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import story_controller_retirements as target
from els_server.domain.dungeon_routes import DungeonRun
from test_tunnel_native_retirements import fixture, OWNER

UNIT = 15
GRAPH_SHA = 'dd9c58d5250519dfa1a4d1bec1893619c304f0e02effb12a672feb092416ab15'
# Pinned stage 0 clear conditions, verbatim from dungeon_lithia_memory5.lua.
PART_CONDITIONS = {
    (0, 1): dict(kind=3, required=[9377], portal_lines=[], delay=0, seconds=0,
                 next=[dict(kind=0, stage=0, part=2, weight=100)]),
    (0, 2): dict(kind=3, required=[9378], portal_lines=[], delay=0, seconds=0,
                 next=[dict(kind=1, stage=1, part=0, weight=100)]),
}
# Route-declared controllers whose retirement ends a part, in declared order.
RELAXED = [(35290, 0, 1, 9377, 2)] + [(35290, 0, 2, 9375, n) for n in (1, 2, 3, 4, 5, 6)] \
          + [(35290, 0, 2, 9378, 7), (35290, 1, 0, 9379, 2)]
PART_CONTROLLERS = [(35290, 0, 1, 9377, 2), (35290, 0, 2, 9378, 7)]


def identity(row):
    return (row['dungeon'], row['stage'], row['part'], row['template'], row['source']['source_index'])


def model_fixture(rule, quest):
    # The first clear run holds only quest 28370 (通关 35290).
    session, event, report, store = fixture(rule, unit=UNIT, quest=quest)
    session.dungeon_run.identity = rule['dungeon']
    session.dungeon_run.stage = rule['stage']
    session.dungeon_run.part = rule['part']
    return session, event, report, store


class Memory5Retirements(unittest.TestCase):
    @property
    def rules(self):
        return [r for r in target.RULES if r['dungeon'] == 35290]

    def call(self, s, e, r, store, *, lease=True):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {
                'els_server.domain.dungeon_equipment_loot_flow': NS(current_lease=lambda actor: lease),
                'els_server.domain.quest_flow': NS(store=lambda actor: store),
                'els_server.domain.dungeon_flow': NS(periodic=lambda actor: [])}))
            return target.handle(s, e, r)

    def test_relaxation_is_limited_to_the_scene_dungeons(self):
        self.assertEqual(sorted({r['dungeon'] for r in target.RULES if r.get('retire_without_quest')}),
                         [35270, 35290, 35320, 35321])
        self.assertEqual([identity(r) for r in self.rules if r.get('retire_without_quest')], RELAXED)
        self.assertEqual([identity(r) for r in self.rules if not r.get('retire_without_quest')],
                         [(35290, 0, 0, 9376, 1), (35290, 1, 0, 9381, 1)])

    def test_first_clear_run_retires_the_part_controllers(self):
        for rule in self.rules:
            if identity(rule) not in PART_CONTROLLERS:
                continue
            with self.subTest(source=identity(rule)):
                self.assertEqual(rule['graph_sha'], GRAPH_SHA)
                s, e, r, store = model_fixture(rule, 28370)
                try:
                    self.assertEqual([x.kind for x in self.call(s, e, r, store)], [0xae, 0xaf])
                    self.assertEqual(store.calls, 1)
                    self.assertEqual(s.dungeon_run.defeated, {r['index']: e.payload})
                    self.assertEqual([x.kind for x in self.call(s, e, r, store)], [0xae])
                    self.assertEqual(store.calls, 1)
                finally:
                    store.db.close()

    def test_accepted_retirement_satisfies_the_pinned_part_condition(self):
        for rule in self.rules:
            if identity(rule) not in PART_CONTROLLERS:
                continue
            with self.subTest(source=identity(rule)):
                s, e, r, store = model_fixture(rule, 28370)
                condition = PART_CONDITIONS[(rule['stage'], rule['part'])]
                others = [dict(key=n, template=9372, active=True, team=1) for n in range(8, 14)]
                npcs = [dict(key=r['index'], template=rule['template'], active=True, team=1)] + others
                waiting = NS(stage=rule['stage'], part=rule['part'], encounter=None,
                             portal_requested=False, defeated={}, retreated=set(), current=dict(npcs=npcs))
                try:
                    self.assertTrue(self.call(s, e, r, store))
                    self.assertFalse(DungeonRun.condition_ready(waiting, condition))
                    cleared = NS(**{**vars(waiting), 'defeated': s.dungeon_run.defeated})
                    self.assertTrue(DungeonRun.condition_ready(cleared, condition))
                finally:
                    store.db.close()

    def test_active_objective_still_credits_the_same_retirement(self):
        rule = next(r for r in self.rules if identity(r) == (35290, 0, 1, 9377, 2))
        s, e, r, store = model_fixture(rule, 28380)
        try:
            self.assertEqual([x.kind for x in self.call(s, e, r, store)], [0xae, 0xaf])
            self.assertEqual(store.calls, 1)
        finally:
            store.db.close()

    def test_source_owner_unit_hp_and_lease_checks_still_reject(self):
        rule = next(r for r in self.rules if identity(r) == (35290, 0, 1, 9377, 2))
        for change in ('source', 'owner', 'hp', 'unit', 'lease'):
            with self.subTest(change=change):
                s, e, r, store = model_fixture(rule, 28370)
                if change == 'source':
                    s.dungeon_run.current['npcs'][0]['points'] = [999999]
                if change == 'owner':
                    r['readiness'] = {OWNER + 1: 0}
                if change == 'hp':
                    r['hp_bits'] = 0
                if change == 'unit':
                    s.account.character = lambda: {'unit_type': 16, 'level': 99}
                try:
                    self.assertEqual(self.call(s, e, r, store, lease=change != 'lease'), [])
                    self.assertFalse(s.dungeon_run.defeated)
                    self.assertEqual(store.calls, 0)
                finally:
                    store.db.close()


if __name__ == '__main__':
    unittest.main()
