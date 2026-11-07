"""Pin the four-gate loot scope decision, so a policy change cannot pass silently.

The report is not a convenience listing: every count here is a claim about what
the running server can and cannot hand a player after a Boss dies. If a future
change edits an acquisition flag or adds a map, these numbers must move on
purpose.
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('loot_scope_report', ROOT / 'tools/loot_scope_report.py')
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def _actors(value):
    """Flatten an npc entry that may carry nested `options` rows."""
    if 'options' in value:
        for row in value['options']:
            yield from _actors(row)
    elif 'template' in value:
        yield value


class LootScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = REPORT.report()
        cls.maps = {row['dungeon']: row for row in cls.data['maps']}

    def test_every_admitted_route_is_accounted_for(self):
        self.assertEqual(self.data['admitted'], 239)
        self.assertEqual(self.data['covered'], 102)
        self.assertEqual(self.data['uncovered'], 137)
        self.assertEqual(len(self.data['maps']), 137)

    def test_buckets_are_finite_and_cover_the_uncovered_maps(self):
        buckets = self.data['buckets']
        self.assertEqual(buckets, {
            'needs_class_evidence': 72,
            'no_native_drop': 30,
            'policy_blocked': 18,
            'reusable_descriptor': 17,
        })
        self.assertEqual(sum(buckets.values()), 137)

    def test_the_native_declaration_covers_almost_every_route(self):
        # Only these admitted routes declare no Boss drop item at all.
        silent = sorted(k for k, v in self.maps.items() if v['bucket'] == 'no_native_drop')
        self.assertEqual(len(silent), 30)
        self.assertNotIn(30000, silent)  # 30000 declares 30163

    def test_acquisition_refusals_keep_their_owner_policy_reasons(self):
        # raid_source_only fell from 97 to 89 because the four chip routes wired
        # this round each declared two raid-only references that are no longer
        # counted among the uncovered maps.
        self.assertEqual(self.data['blocked_reasons'], {
            'accessory_compatibility_only': 68,
            'cartridge_use_only': 15,
            'policy_blocked_type_6': 5,
            'raid_source_only': 89,
        })

    def test_a_classic_map_is_blocked_by_the_accessory_flag_not_by_missing_data(self):
        row = self.maps[30000]
        self.assertEqual(row['bucket'], 'policy_blocked')
        self.assertEqual(row['native_members'], [30163])
        self.assertEqual(row['reusable'], [])
        self.assertEqual([b['reason'] for b in row['blocked']], ['accessory_compatibility_only'])

    def test_reusable_routes_point_at_descriptors_that_already_exist(self):
        reusable = sorted(k for k, v in self.maps.items() if v['bucket'] == 'reusable_descriptor')
        self.assertEqual(len(reusable), 17)
        self.assertIn(35170, reusable)
        self.assertEqual([r['descriptor'] for r in self.maps[35170]['reusable']], ['ordinary-material-default-v1'])
        self.assertIn(35370, reusable)
        self.assertEqual([r['descriptor'] for r in self.maps[35370]['reusable']], ['equipment-fragment-v1'])
        # 16 chip routes remain unwired (16 of the 22 chip routes are raid-managed
        # and 4 were wired this round); the rest share one template and generator.
        chip = [k for k in reusable if k != 35170]
        self.assertEqual(len(chip), 16)
        for identity in chip:
            self.assertEqual([r['template'] for r in self.maps[identity]['reusable']], [118638])

    def test_a_fully_no_drop_graph_is_not_a_descriptor_shortage(self):
        """35170 has a reusable descriptor but no hostile drop in its own graph.

        Every actor in dungeon_devildom2_secret.lua carries no_drop=true, the
        Boss (template 9180) included, so the material catalog's structural
        `if not sources` guard refuses it. That is a native statement about the
        map, not a missing local descriptor, and must not be forced.
        """
        from els_server.domain import dungeon_material_loot_catalog as material
        from els_server.domain.dungeon_routes import route_catalog
        routes = route_catalog()._data
        graph = routes['graphs'][routes['routes']['35170']['source']]
        actors = [a
                  for stage in graph['stages'].values()
                  for part in stage['parts'].values()
                  for group in part['groups']
                  for entry in group['npcs']
                  for a in _actors(entry)]
        self.assertTrue(actors)
        self.assertTrue(all(a['no_drop'] for a in actors))
        self.assertIn(35170, {row['dungeon'] for row in self.data['maps']})
        self.assertNotIn(35170, material.MAPS)
        self.assertNotIn(35170, {int(k) for k in material.catalog()['maps']})

    def test_every_bucket_claim_is_consistent_with_its_parts(self):
        for row in self.data['maps']:
            bucket = row['bucket']
            described = bool(row['reusable'])
            grantable = bool(row['grantable_but_undescribed']) or described
            if bucket == 'no_native_drop':
                self.assertEqual(row['native_members'], [], row['dungeon'])
                self.assertFalse(grantable, row['dungeon'])
            elif bucket == 'reusable_descriptor':
                self.assertTrue(described, row['dungeon'])
            elif bucket == 'needs_class_evidence':
                self.assertFalse(described, row['dungeon'])
                self.assertTrue(grantable, row['dungeon'])
            elif bucket == 'policy_blocked':
                self.assertFalse(grantable, row['dungeon'])
                self.assertTrue(row['blocked'], row['dungeon'])
            else:
                self.fail(f'unknown bucket {bucket}')

    def test_grantable_and_blocked_partition_the_declared_template_set(self):
        for row in self.data['maps']:
            blocked = {b['template'] for b in row['blocked']}
            grantable = set(row['grantable_but_undescribed']) | {r['template'] for r in row['reusable']}
            self.assertEqual(set(row['native_members']), blocked | grantable, row['dungeon'])
            self.assertFalse(blocked & grantable, row['dungeon'])


if __name__ == '__main__':
    unittest.main()
