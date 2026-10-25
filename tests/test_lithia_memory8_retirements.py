"""LITHIA_MEMORY8 (35320/35321) retires its stage-1 controller on the scene timeline.

Server log 20261025-165751, run 647e51da-9465-417b-94e1-56db7a7e01dc: stage 0 cleared
(both 9440 retirements recorded), then the player worked through stage 1 part 0, which
declares 24 actors under one kind 0 condition.  Of the 204 0x202/0xad death reports the
session logged, 202 got their 0xae.  The first miss (request 676, 17:00:32.174) names no
actor the lifecycle records touched in that window and is left unattributed.  The second
is request 5511 at 17:12:44.946, 160 bytes - the killerless expiry shape - and the client
lifecycle record 13 ms earlier names key 4, which is template 9433
(LITHIA_MEMORY8_PLANT_DROSERA), not the controller.  Key 9 = template 9450
(LITHIA_MEMORY8_STORY_DUMMY_1.lua, 1000 HP) was never reported at all: it stayed at full
HP in every following frame, the frames kept mode=2 substage=1 for 92 more seconds and
the player left at 17:14:19 without a clear.
So the frozen part had two halves, and this module fixes the one the plant is not.

9450 is one of the 18 actors the condition waits on, and it can only retire through
this rule: a credited kill of it is refused by design (the rule requires the native 255
report), and its own script is what removes it.  That rule names epic quest 28550
(ClearType 2, kill 9450 once), and 28550 is accepted only after 28540 is turned in at
NPC 10394, while 28540's own objective is ClearType 26 = visit 35320 - the very run that
has to pass this part.  Following the merged 35270/35290 relaxation, a quest that cannot
be active yet must not strand the scene; quest credit still needs an active matching
quest, so accepting this retirement grants no progress.  The other half - the plant
expiry that got no acknowledgement - is test_lithia_memory8_plant_expiry.
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
VISIT_QUEST = 28540
OBJECTIVE_QUEST = 28550
# The retirement this scene waits for, in the exact declared order.
RELAXED = [(35320, 1, 0, 9450, 10), (35321, 0, 0, 9450, 10)]
STAGE1_PART0 = (35320, 1, 0)


def identity(row):
    return (row['dungeon'], row['stage'], row['part'], row['template'], row['source']['source_index'])


def model_fixture(rule, quest):
    # The first visit run holds only 28540; 28550 comes after the turn-in.
    session, event, report, store = fixture(rule, unit=UNIT, quest=quest)
    session.dungeon_run.identity = rule['dungeon']
    session.dungeon_run.stage = rule['stage']
    session.dungeon_run.part = rule['part']
    return session, event, report, store


class Memory8Retirements(unittest.TestCase):
    @property
    def rules(self):
        return [r for r in target.RULES if r['dungeon'] in (35320, 35321)]

    def call(self, s, e, r, store, *, lease=True):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {
                'els_server.domain.dungeon_equipment_loot_flow': NS(current_lease=lambda actor: lease),
                'els_server.domain.quest_flow': NS(store=lambda actor: store),
                'els_server.domain.dungeon_flow': NS(periodic=lambda actor: [])}))
            return target.handle(s, e, r)

    def test_relaxation_is_limited_to_the_stage_one_controller(self):
        self.assertEqual([identity(r) for r in self.rules if r.get('retire_without_quest')], RELAXED)
        self.assertEqual([identity(r) for r in self.rules if not r.get('retire_without_quest')],
                         [(35320, 0, 0, 9440, 1), (35320, 0, 3, 9440, 9), (35320, 2, 0, 9451, 11),
                          (35320, 3, 0, 9452, 5), (35320, 3, 0, 9441, 6), (35320, 3, 0, 9453, 7),
                          (35320, 3, 0, 9455, 8), (35321, 1, 0, 9451, 11), (35321, 2, 0, 9452, 5),
                          (35321, 2, 0, 9441, 6), (35321, 2, 0, 9453, 7), (35321, 2, 0, 9455, 8)])

    def test_visit_run_retires_the_part_controller(self):
        for rule in self.rules:
            if identity(rule) not in RELAXED:
                continue
            with self.subTest(source=identity(rule)):
                s, e, r, store = model_fixture(rule, VISIT_QUEST)
                try:
                    self.assertEqual([x.kind for x in self.call(s, e, r, store)], [0xae, 0xaf])
                    self.assertEqual(store.calls, 1)
                    self.assertEqual(s.dungeon_run.defeated, {r['index']: e.payload})
                    self.assertEqual([x.kind for x in self.call(s, e, r, store)], [0xae])
                    self.assertEqual(store.calls, 1)
                finally:
                    store.db.close()

    def test_active_objective_still_credits_the_same_retirement(self):
        for rule in self.rules:
            if identity(rule) not in RELAXED:
                continue
            with self.subTest(source=identity(rule)):
                s, e, r, store = model_fixture(rule, OBJECTIVE_QUEST)
                try:
                    self.assertEqual([x.kind for x in self.call(s, e, r, store)], [0xae, 0xaf])
                    self.assertEqual(store.calls, 1)
                finally:
                    store.db.close()

    def test_retirement_satisfies_the_pinned_kind_zero_condition(self):
        dungeon, stage, part = STAGE1_PART0
        run = DungeonRun(dungeon, '00000000-0000-4000-8000-000000000001')
        run._load_stage(stage)
        run.part = part
        controller = next(n for n in run.current['npcs'] if n['template'] == 9450)
        self.assertEqual((controller['key'], controller['source_index'], controller['hp']),
                         (9, 10, 1000))
        condition = run.current['conditions'][0]
        self.assertEqual((condition['kind'], condition['next'][0]['stage'], condition['next'][0]['part']),
                         (0, 2, 0))
        waiting = {n['key'] for n in run.current['npcs']
                   if n['active'] and n.get('team', 1) != 0 and n['template'] != 9450}
        run.defeated = dict.fromkeys(waiting, b'hostiles')
        self.assertFalse(run.condition_ready(condition))
        run.defeated = {**dict.fromkeys(waiting, b'hostiles'), controller['key']: b'retirement'}
        self.assertTrue(run.condition_ready(condition))

    def test_source_owner_unit_hp_and_lease_checks_still_reject(self):
        rule = next(r for r in self.rules if identity(r) == (35320, 1, 0, 9450, 10))
        for change in ('source', 'owner', 'hp', 'unit', 'lease'):
            with self.subTest(change=change):
                s, e, r, store = model_fixture(rule, VISIT_QUEST)
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
