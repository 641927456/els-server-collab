"""Trosh (Devildom2 residence, map 34340) uses the approved battle HP rule.

The native script declares ``MAX_HP 1500`` for the three residence boss
templates, which is a script-side placeholder: the boss dies to a single hit.
The adopted local rule keeps that script evidence (``fixed``/``expected_script_hp``)
and replaces only the battle maximum, and only for the exact map, level and
template identity it was approved for.
"""
import hashlib
import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data'
MAP = 34340
TEMPLATES = (7584, 7585, 7586)
APPROVED_HP = 758272320.0
SCRIPT_HP = 1500


class TroshBattleHpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from els_server.domain.dungeon_routes import route_catalog
        cls.catalog = route_catalog()

    def policy(self):
        from els_server.domain import formal_npc_hp as hp
        return hp.policy()

    def test_payload_and_manifest_identity_still_holds(self):
        raw = (DATA / 'formal_npc_hp.json').read_bytes()
        manifest = json.loads((DATA / 'formal_npc_hp.manifest.json').read_bytes())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['payload_sha256'])
        self.assertEqual(self.policy()['policy'], 'formal-server-npc-hp-20261025-v1')

    def test_all_three_trosh_templates_report_the_approved_maximum(self):
        from els_server.domain.formal_npc_hp import maximum
        for template in TEMPLATES:
            with self.subTest(template=template):
                self.assertEqual(maximum(self.catalog, template, dungeon=MAP, npc_level=99), APPROVED_HP)

    def test_the_approved_maximum_survives_float32_exactly(self):
        from els_server.domain.formal_npc_hp import f32
        self.assertEqual(f32(APPROVED_HP), APPROVED_HP)
        self.assertEqual(struct.unpack('<f', struct.pack('<f', APPROVED_HP))[0], APPROVED_HP)

    def test_the_override_is_bound_to_the_exact_level(self):
        from els_server.domain.formal_npc_hp import maximum
        for level in (1, 98, 100):
            with self.subTest(level=level), self.assertRaises(ValueError):
                maximum(self.catalog, 7584, dungeon=MAP, npc_level=level)

    def test_the_override_is_bound_to_the_exact_map(self):
        from els_server.domain.formal_npc_hp import maximum
        # The other Devildom2 graphs keep the retained script maximum: the rule
        # is registered per map, so it cannot leak to a sibling dungeon.
        for dungeon in (34350, 34360):
            with self.subTest(dungeon=dungeon):
                self.assertEqual(maximum(self.catalog, 7584, dungeon=dungeon, npc_level=99), SCRIPT_HP)

    def test_no_other_map_or_template_carries_an_override(self):
        policy = self.policy()
        carrying = sorted(key for key, row in policy['maps'].items() if 'combat_hp_overrides' in row)
        self.assertEqual(carrying, [str(MAP)])
        self.assertEqual(sorted(policy['maps'][str(MAP)]['combat_hp_overrides']), ['7584', '7585', '7586'])

    def test_the_script_evidence_is_retained_next_to_the_override(self):
        policy = self.policy()
        for template in TEMPLATES:
            with self.subTest(template=template):
                row = policy['templates'][str(template)]
                self.assertEqual(row['source'], 'current_client_explicit')
                self.assertEqual(row['fixed'], SCRIPT_HP)
                override = policy['maps'][str(MAP)]['combat_hp_overrides'][str(template)]
                self.assertEqual(override['expected_script_hp'], SCRIPT_HP)
                self.assertEqual(override['hp'], APPROVED_HP)
                self.assertEqual(override['hp_float32'], APPROVED_HP)
                self.assertEqual(override['level'], policy['maps'][str(MAP)]['level'])
                self.assertEqual(override['local_policy'], 'trosh-battle-hp-correction-20261101-v1')
                self.assertFalse(override['official_CN_claim'])
                for key in ('enum', 'script', 'class_id', 'is_npc'):
                    self.assertEqual(override[key], row[key])

    def test_other_templates_on_the_same_map_keep_their_imported_maximum(self):
        from els_server.domain.formal_npc_hp import f32, public_maximum
        policy = self.policy()
        for template, row in policy['maps'][str(MAP)]['public_hp_templates'].items():
            if int(template) in TEMPLATES:
                continue
            with self.subTest(template=template):
                self.assertEqual(public_maximum(self.catalog, int(template), MAP, row['level']), f32(row['hp_float32']))


if __name__ == '__main__':
    unittest.main()
