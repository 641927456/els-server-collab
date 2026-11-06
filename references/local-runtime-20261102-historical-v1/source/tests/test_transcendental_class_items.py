"""Transcendence and master-class item registrations.

Evidence: analysis/client-6c6b5180/20261014-215604/job-resources/
TranscendentalClassItem.tables.json — 697 AddTranscendentalClassItem calls
(110/480/107 for stages 0/1/2), 242 AddMasterClassItem calls over 61 classes, and
15 AddTranscendentalUnitType registrations.

Why it matters: careers.json carries 541 advancement rules but covers only 361 of
these 697 transcendental items and 60 of the 242 master-class items. The numbers
below pin that gap so it cannot quietly be read as full coverage.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from els_server.domain import enums, transcendental_class_items as tci
from els_server.game_data import CLIENT_SHA

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data/transcendental_class_items.json'
CAREERS = ROOT / 'els_server/data/careers.json'


class TranscendentalPayload(unittest.TestCase):
    def setUp(self):
        tci._payload.cache_clear()
        self.payload = json.loads(DATA.read_text(encoding='utf8'))

    def test_payload_pins_the_current_client(self):
        self.assertEqual(self.payload['client_sha256'], CLIENT_SHA)
        self.assertEqual(self.payload['schema_version'], 1)

    def test_the_registration_counts_are_exact(self):
        summary = tci.summary()
        self.assertEqual(summary['transcendental_items'], 697)
        self.assertEqual(summary['master_class_items'], 242)
        self.assertEqual(summary['items'], 699)
        self.assertEqual(summary['registered_in_both'], 240)
        self.assertEqual(summary['stage_histogram'], {'0': 110, '1': 480, '2': 107})
        self.assertEqual(len(tci.items()), 699)

    def test_every_item_answers_at_least_one_question(self):
        for item_id, entry in tci.items().items():
            self.assertTrue('transcendental_stage' in entry or 'master_unit_class' in entry,
                            item_id)

    def test_stage_lookup_matches_the_histogram(self):
        for stage, count in ((0, 110), (1, 480), (2, 107)):
            self.assertEqual(len(tci.items_with_stage(stage)), count, stage)

    def test_every_master_class_id_agrees_with_the_enum(self):
        for item_id, entry in tci.items().items():
            if 'master_unit_class' not in entry:
                continue
            self.assertEqual(
                enums.value('UNIT_CLASS', entry['master_unit_class']),
                entry['master_unit_class_id'], item_id)

    def test_every_master_class_has_four_items_except_one(self):
        counts = {}
        for entry in tci.items().values():
            if 'master_unit_class' in entry:
                counts[entry['master_unit_class']] = counts.get(
                    entry['master_unit_class'], 0) + 1
        self.assertEqual(len(counts), 61)
        self.assertEqual(sorted(counts.values()).count(4), 60)
        self.assertEqual(sorted(counts.values()).count(2), 1)

    def test_master_class_lookup_accepts_both_spellings(self):
        single = tci.items_for_master_class('UC_ELSWORD_KNIGHT_EMPEROR')
        self.assertEqual(single, tci.items_for_master_class('UNIT_CLASS.UC_ELSWORD_KNIGHT_EMPEROR'))
        self.assertEqual(single, (711129, 711130, 711131, 711132))
        self.assertEqual(tci.master_class(single[0]), 'UC_ELSWORD_KNIGHT_EMPEROR')

    def test_only_the_fifteen_registered_unit_types_can_transcend(self):
        self.assertEqual(len(tci.unit_types()), 15)
        self.assertTrue(tci.can_transcend('UT_ELSWORD'))
        self.assertTrue(tci.can_transcend('UNIT_TYPE.UT_LITHIA'))
        # Present in the client UNIT_TYPE table but never registered.
        self.assertFalse(tci.can_transcend('UT_NONE'))
        self.assertFalse(tci.can_transcend('UT_END'))
        self.assertFalse(tci.can_transcend('UT_NO_SUCH_CLASS'))
        for symbol, number in tci.unit_types().items():
            self.assertEqual(enums.value('UNIT_TYPE', symbol), number)

    def test_a_master_item_keeps_both_registrations(self):
        # 240 items are registered as a stage-1 transcendental item *and* as a
        # master-class item; collapsing them would lose one of the two answers.
        both = [item_id for item_id, entry in tci.items().items()
                if 'transcendental_stage' in entry and 'master_unit_class' in entry]
        self.assertEqual(len(both), 240)
        self.assertTrue(all(tci.stage(item_id) == 1 for item_id in both))

    def test_unknown_items_return_none_rather_than_guessing(self):
        self.assertIsNone(tci.item(1))
        self.assertIsNone(tci.stage(1))
        self.assertIsNone(tci.master_class(1))
        self.assertEqual(tci.items_for_master_class('UC_NO_SUCH_CLASS'), ())
        self.assertEqual(tci.items_with_stage(9), ())


class CareersCoverageGap(unittest.TestCase):
    """The gap this import closes, pinned so it cannot be read as full coverage."""

    def setUp(self):
        self.rules = {int(key) for key in
                      json.loads(CAREERS.read_text(encoding='utf8'))['rules']}
        tci._payload.cache_clear()

    def test_careers_only_covers_half_of_the_transcendental_items(self):
        items = tci.items()
        transcendental = {i for i, e in items.items() if 'transcendental_stage' in e}
        master = {i for i, e in items.items() if 'master_unit_class' in e}
        self.assertEqual(len(self.rules), 541)
        self.assertEqual(len(transcendental - self.rules), 336)
        self.assertEqual(len(master - self.rules), 182)
        self.assertEqual(len((transcendental | master) - self.rules), 338)

    def test_the_gap_is_a_real_hole_not_a_superset_problem(self):
        # 361 transcendental and 60 master items do overlap careers.json, so the
        # two sources agree where they meet; the missing part is genuinely missing.
        items = tci.items()
        transcendental = {i for i, e in items.items() if 'transcendental_stage' in e}
        master = {i for i, e in items.items() if 'master_unit_class' in e}
        self.assertEqual(len(transcendental & self.rules), 361)
        self.assertEqual(len(master & self.rules), 60)


if __name__ == '__main__':
    unittest.main()
