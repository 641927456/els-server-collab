"""Public encounter controllers retire independently of optional epic quests.

Eleven character-story controllers used to demand an earned optional epic quest
before the receiver accepted the native 255 report, so a character that walked
into the room legitimately still could not finish it. public_controller_rules
adds those eleven rows and story_controller_retirements.rules_for lets them
override the story row of the same identity.

The rows are byte-identical to the story rows except quest_independent (and, on
a few, requires_native_255). No quest list, source pin, HP or class is widened.

Every assertion runs on the in-memory model from test_tunnel_native_retirements;
the original HP identity is patched because that model has no graph catalog.
Storage atomicity and the live wire have their separate runtime proof.
"""
import sys
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import story_controller_retirements as target
from els_server.domain.public_controller_rules import RULES as PUBLIC
from test_tunnel_native_retirements import fixture

# The exact sources the release adds: seven maps, eleven actors.
ADDED = ((34240, 1, 0, 7407, 1), (34250, 0, 1, 7428, 1), (34260, 1, 3, 7449, 1),
         (34300, 0, 1, 7500, 1), (34300, 3, 0, 7502, 2), (34600, 2, 0, 8025, 3),
         (34620, 0, 0, 8058, 3), (34620, 1, 0, 8059, 2), (34680, 0, 0, 8142, 9),
         (34680, 0, 1, 8142, 10), (34680, 1, 0, 8142, 5))

# A story row no public row covers: its quest gate must survive.
GATED = (35260, 0, 0, 9319, 12)


def identity(row):
    return tuple(row[k] for k in ('dungeon', 'stage', 'part', 'template')) + (row['source']['source_index'],)


def public_rule(key):
    return next(r for r in PUBLIC if identity(r) == key)


def story_rule(key):
    return next(r for r in target.RULES if identity(r) == key)


class PublicRuleTable(unittest.TestCase):
    def test_the_table_is_the_original_public_set_plus_eleven_story_rows(self):
        self.assertEqual(len(PUBLIC), 146)
        self.assertEqual(sum(1 for r in PUBLIC if 'units' in r), 135)
        self.assertEqual({identity(r) for r in PUBLIC if 'unit' in r}, set(ADDED))
        self.assertEqual({r['dungeon'] for r in PUBLIC if 'unit' in r},
                         {34240, 34250, 34260, 34300, 34600, 34620, 34680})

    def test_added_rows_drop_only_the_quest_requirement(self):
        for key in ADDED:
            added, story = public_rule(key), story_rule(key)
            self.assertTrue(added['quest_independent'], key)
            self.assertTrue(added['requires_native_255'], key)
            changed = {name for name in set(added) | set(story) if added.get(name) != story.get(name)}
            self.assertEqual(changed - {'quest_independent', 'requires_native_255'}, set(), key)
            # The optional quest list stays on the row; it is no longer a gate.
            self.assertEqual(added['map_quests'], story['map_quests'], key)
            self.assertEqual((added['hp'], added['graph_sha'], added['source']),
                             (story['hp'], story['graph_sha'], story['source']), key)

    def test_every_original_public_row_covers_all_fifteen_classes(self):
        for row in PUBLIC:
            if 'units' in row:
                self.assertEqual(row['units'], list(range(1, 16)), row['dungeon'])


class RuleDispatch(unittest.TestCase):
    def test_the_added_row_wins_over_the_story_row_of_the_same_identity(self):
        for key in ADDED:
            with self.subTest(source=key):
                self.assertNotIn('quest_independent', story_rule(key))
                resolved = {identity(r): r for r in target.rules_for(NS(identity=key[0]))}
                self.assertTrue(resolved[key]['quest_independent'])

    def test_story_only_identities_keep_their_gate(self):
        rules = {identity(r): r for r in target.rules_for(NS(identity=35260))}
        self.assertIn(GATED, rules)
        self.assertNotIn('quest_independent', rules[GATED])
        self.assertEqual(rules[GATED]['unit'], 15)

    def test_a_public_only_dungeon_now_answers_instead_of_returning_none(self):
        self.assertEqual({identity(r) for r in target.rules_for(NS(identity=34370))},
                         {identity(r) for r in PUBLIC if r['dungeon'] == 34370})
        self.assertEqual(target.rules_for(NS(identity=999999)), ())


class Native255Admission(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(sys.modules, {
            'els_server.domain.dungeon_equipment_loot_flow': NS(current_lease=lambda actor: True),
            'els_server.domain.dungeon_flow': NS(periodic=lambda actor: []),
        }))

    def call(self, rule, *, quest, unit=None):
        if unit is None:
            unit = rule['units'][0] if 'units' in rule else rule['unit']
        session, event, report, store = fixture(rule, unit=unit, quest=quest)
        run = session.dungeon_run
        run.identity, run.stage, run.part = rule['dungeon'], rule['stage'], rule['part']
        self.stack.enter_context(patch.dict(sys.modules, {'els_server.domain.quest_flow': NS(store=lambda actor: store)}))
        self.stack.enter_context(patch.object(target, 'initialized_maximum', lambda run, source: rule['hp']))
        return target.handle(session, event, report), session, store

    def test_the_added_sources_retire_without_an_earned_quest(self):
        for key in ADDED:
            with self.subTest(source=key):
                replies, session, store = self.call(public_rule(key), quest=0)
                self.assertEqual([x.kind for x in replies], [0xae, 0xaf])
                self.assertEqual(store.calls, 1)
                self.assertEqual(len(session.dungeon_run.defeated), 1)

    def test_a_story_only_source_still_needs_its_quest(self):
        rule = story_rule(GATED)
        # The handler turns the quest rejection into no reply, not an exception.
        replies, session, store = self.call(rule, quest=0)
        self.assertEqual(replies, [])
        self.assertFalse(session.dungeon_run.defeated)
        self.assertEqual(store.calls, 1)
        replies, session, store = self.call(rule, quest=28140)
        self.assertEqual([x.kind for x in replies], [0xae, 0xaf])
        self.assertEqual(store.calls, 1)

    def test_a_foreign_class_is_still_refused(self):
        for key in ADDED:
            with self.subTest(source=key):
                replies, session, store = self.call(public_rule(key), quest=0, unit=16)
                self.assertEqual(replies, [])
                self.assertFalse(session.dungeon_run.defeated)
                self.assertEqual(store.calls, 0)


if __name__ == '__main__':
    unittest.main()
