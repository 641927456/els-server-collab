"""Portable checks for the exact paired review source and public policy edges."""
from pathlib import Path
import datetime as dt
import hashlib
import importlib.util
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / 'references/silver-mirror-completion-20261025-v1'
spec = importlib.util.spec_from_file_location(
    'silver_mirror_review_policy',
    REVIEW / 'shared/els_server/domain/silver_mirror_policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class SilverMirrorReview(unittest.TestCase):
    def test_exact_paired_sources(self):
        index = json.loads((REVIEW / 'source-index.json').read_bytes())
        self.assertEqual(set(index['channels']), {'online', 'local'})
        for channel in index['channels'].values():
            self.assertEqual(len(channel['files']), 28)
            for row in channel['files']:
                path = (REVIEW / row['source']).resolve()
                self.assertTrue(path.is_relative_to(REVIEW.resolve()))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row['sha256'])
                self.assertEqual(path.stat().st_size, row['size'])

    def test_reset_and_deployment_window(self):
        reset = dt.datetime(2026, 10, 28, 10, tzinfo=policy.UTC8).timestamp()
        self.assertEqual(policy.week_start(reset - .001), reset - 7 * 86400)
        self.assertEqual(policy.week_start(reset), reset)
        self.assertFalse(policy.blackout(reset - 601))
        self.assertTrue(policy.blackout(reset - 600))
        self.assertTrue(policy.blackout(reset + 599))
        self.assertFalse(policy.blackout(reset + 600))

    def test_stable_shared_layout_and_no_stage_skip(self):
        week = policy.week_start(dt.datetime(2026, 10, 25, tzinfo=policy.UTC8).timestamp())
        for n in range(52):
            current = week + n * 7 * 86400
            normal, special = policy.layout(current)
            self.assertEqual(policy.layout(current), (normal, special))
            self.assertEqual(len({policy.FAMILY[d] for d in normal}), 3)
            with self.assertRaises(ValueError):
                policy.eligible(current, 0, 0, normal[2])
            self.assertEqual(policy.deployed(current, 4)[2], special)

    def test_five_weekly_awards_then_exhausted(self):
        week = policy.week_start(dt.datetime(2026, 10, 25, tzinfo=policy.UTC8).timestamp())
        memory, remaining, progress = 0, 5, 0
        observed = []
        for cycle in range(6):
            layout = policy.deployed(week, memory)
            for dungeon in layout:
                result = policy.cleared(week, memory, progress, remaining, dungeon)
                memory, remaining, progress = (result[k] for k in ('memory', 'remaining', 'progress'))
            observed.append((remaining, memory, result['weekly']))
        self.assertEqual(observed, [(4, 1, True), (3, 2, True), (2, 3, True),
                                    (1, 4, True), (0, 0, True), (0, 0, False)])

    def test_story_practice_does_not_touch_normal_progress(self):
        week = policy.week_start(dt.datetime(2026, 10, 25, tzinfo=policy.UTC8).timestamp())
        for dungeon in set(policy.STORY.values()):
            result = policy.cleared(week, 3, 1, 2, dungeon)
            self.assertEqual((result['memory'], result['progress'], result['remaining']), (3, 1, 2))
            self.assertFalse(result['weekly'])
            self.assertFalse(result['clear_buffs'])


if __name__ == '__main__':
    unittest.main()
