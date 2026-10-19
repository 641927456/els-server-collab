"""Verified roster reuse without shared mutable state or altered spawn bytes."""
import json
import unittest
from unittest.mock import patch

from els_server.domain import dungeon_population as roster


class PopulationCacheTests(unittest.TestCase):
    def setUp(self):
        roster._verified_population.cache_clear()

    def tearDown(self):
        roster._verified_population.cache_clear()

    def test_warm_death_path_needs_no_files_or_catalog_queries(self):
        expected = roster.population(0)
        with patch.object(roster.Path, 'read_text', side_effect=AssertionError('roster reread')), \
             patch.object(roster.Path, 'read_bytes', side_effect=AssertionError('source reread')), \
             patch.object(roster, 'client_data', side_effect=AssertionError('catalog lookup')):
            self.assertEqual(roster.population(0), expected)

    def test_returned_nested_objects_are_isolated(self):
        expected = roster.population(2)
        packet = roster.substage(2).payload
        changed = roster.population(2)
        changed['npcs'][0]['template'] = -1
        changed['npcs'][0]['source_group'].clear()
        changed['npcs'].clear()
        self.assertEqual(roster.population(2), expected)
        self.assertEqual(roster.substage(2).payload, packet)
        roster.substage(2, boss_gauge=True)
        self.assertEqual(roster.substage(2).payload, packet)

    def test_failed_verification_is_not_cached(self):
        with patch.object(roster.Path, 'read_bytes', return_value=b'changed source'):
            with self.assertRaisesRegex(ValueError, 'Population source changed'):
                roster.population(0)
        self.assertEqual(roster._verified_population.cache_info().currsize, 0)
        self.assertEqual(roster.population(0)['index'], 0)

    def test_all_stages_preserve_original_wire_and_reject_invalid_indices(self):
        # Compare to the unmodified source fixture after the normal verifier.
        fixture = json.loads((roster.ROOT / 'population-test-fixture.json').read_text(encoding='utf8'))
        for stage in range(3):
            self.assertEqual(roster.population(stage), fixture['stages'][stage])
        for stage in (True, 0.0, -1, 3, '0', None):
            with self.assertRaises(ValueError):
                roster.population(stage)


if __name__ == '__main__':
    unittest.main()
