"""Original PR597 source contamination must fail the existing materializer.

Only immutable historical inputs are pinned. The current default may advance
through any independently valid profile and source mapping.
"""
from pathlib import Path
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from tools import materialize_formal_runtime as materializer

ROOT = Path(__file__).resolve().parents[1]
LOOT_PATH = "els_server/data/dungeon_equipment_loot.json"
NEGATIVE_SOURCE = ROOT / "tests/fixtures/pr597_dungeon_equipment_loot_v2_rejected.json"
ORIGINAL_SHA = "31a5c4c5d7a677f67d01744cc76570c46ca503a9a4fa7d1b30dc3b2ef656eea5"
NEGATIVE_SHA = "8fa0415a2bad6cafd741b948ddfc940b7bad565a59f1bf1d88e556bf7f719fa1"
HISTORICAL = (
    ("channels/reviewed-pr563-573-576-current-20261027-v1.json",
     "42cd36e9f41d21788e4f367d2a5652bda6a6e15c744ef730908073eef599e681"),
    ("channels/reviewed-pr563-573-576-peak-parent-20261027-v2.json",
     "0d1e9a05ddd89cbf226ae7157515ca5dc26ca33ab09d00cd4d8509d56e595f06"),
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def historical_profiles():
    for name, expected in HISTORICAL:
        raw = (ROOT / name).read_bytes()
        if digest(raw) != expected:
            raise AssertionError("Historical profile bytes changed: " + name)
        yield name, json.loads(raw)


def loot_entry(profile, channel):
    return next(row for row in profile["channels"][channel]["files"]
                if row["path"] == LOOT_PATH)


class PR597SourceContractTests(unittest.TestCase):
    def negative_fixture(self):
        raw = NEGATIVE_SOURCE.read_bytes()
        self.assertEqual(len(raw), 4773)
        self.assertEqual(digest(raw), NEGATIVE_SHA)
        return NEGATIVE_SOURCE

    def candidate_source_only(self, original_bound, negative):
        def bound(repo, value):
            if Path(repo).resolve() == ROOT.resolve() and value == LOOT_PATH:
                return negative
            return original_bound(repo, value)
        return bound

    def test_historical_profiles_are_byte_frozen(self):
        # These are historical freeze bytes, never the advancing default head.
        self.assertEqual(len(list(historical_profiles())), 2)

    def test_current_and_historical_legal_sources_pass(self):
        for name, profile in historical_profiles():
            for channel in ("online", "local"):
                with self.subTest(profile=name, channel=channel):
                    entry = loot_entry(profile, channel)
                    self.assertEqual(entry, dict(path=LOOT_PATH, source=LOOT_PATH,
                                                 size=3422, sha256=ORIGINAL_SHA))
                    materializer.verify(ROOT / LOOT_PATH, entry)
                    materializer.plan(ROOT, profile, channel)
        # Check the live default by its own declared source contract. No release,
        # parent SHA, candidate count or current loot SHA is hard-coded here.
        current = materializer.load_manifest(ROOT / "channels/current-engine.json", ROOT)
        for channel in ("online", "local"):
            with self.subTest(current_default_channel=channel):
                rows = materializer.plan(ROOT, current, channel)
                entry, source = next((row, source) for row, source in rows
                                     if row["path"] == LOOT_PATH)
                self.assertIsNotNone(source)
                materializer.verify(source, entry)

    def test_old_pr597_source_is_rejected_by_original_size(self):
        negative = self.negative_fixture()
        original_bound = materializer.bound
        for name, profile in historical_profiles():
            for channel in ("online", "local"):
                with self.subTest(profile=name, channel=channel):
                    # Only the one candidate source is substituted. Every other
                    # source still uses the real bound/verify/plan functions.
                    with patch.object(materializer, "bound", side_effect=
                                      self.candidate_source_only(original_bound, negative)):
                        with self.assertRaisesRegex(ValueError, "Missing or wrong size: " + LOOT_PATH):
                            materializer.plan(ROOT, profile, channel)

    def test_size_only_forgery_is_rejected_by_original_hash(self):
        negative = self.negative_fixture()
        original_bound = materializer.bound
        for name, original in historical_profiles():
            for channel in ("online", "local"):
                profile = copy.deepcopy(original)
                loot_entry(profile, channel)["size"] = 4773
                with self.subTest(profile=name, channel=channel):
                    # A counterfactual in-memory size edit must still fail the
                    # original frozen SHA. No source/profile file is written.
                    with patch.object(materializer, "bound", side_effect=
                                      self.candidate_source_only(original_bound, negative)):
                        with self.assertRaisesRegex(ValueError, "Hash mismatch: " + LOOT_PATH):
                            materializer.plan(ROOT, profile, channel)
        # The negative controls cannot silently rewrite either historical file.
        self.assertEqual(len(list(historical_profiles())), 2)


if __name__ == "__main__":
    unittest.main()
