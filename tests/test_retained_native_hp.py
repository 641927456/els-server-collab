"""Approved finite HP inputs and original native Hero/Boss initialization."""
import hashlib
import json
import struct
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data'


def local(dungeon, value):
    """The published maximum of a source value after the local playability overlay."""
    from els_server.domain.local_hp_curve import apply
    return apply(dungeon, value)


def attributes(initializer):
    cursor = 5
    for index in range(6):
        if index == 4:
            assert initializer[cursor] == 1
            cursor += 1
        length = struct.unpack_from('>I', initializer, cursor)[0]
        cursor += 4 + length
    assert len(initializer) - cursor == 98
    return initializer[cursor:cursor + 97]


class FinitePolicyFilesTests(unittest.TestCase):
    def test_all_four_payloads_match_their_manifests_and_client(self):
        from els_server.game_data import CLIENT_SHA
        for name in ('formal_npc_hp', 'boss_npc_stats', 'native_hero_inputs', 'raid_npc_stats'):
            with self.subTest(name=name):
                raw = (DATA / (name + '.json')).read_bytes()
                policy = json.loads(raw)
                manifest = json.loads((DATA / (name + '.manifest.json')).read_bytes())
                self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest['payload_sha256'])
                self.assertEqual(policy['client_sha256'], CLIENT_SHA)
                self.assertEqual(manifest['client_sha256'], CLIENT_SHA)

    def test_component_priority_is_finite_and_registered_in_current_client(self):
        from els_server.npc_data import NpcData
        from els_server.game_data import CLIENT_SHA
        manifest = json.loads((DATA / 'client/manifest.json').read_bytes())
        enum_sha = next(row['sha256'] for row in manifest['sources'] if row['name'] == 'Enum.lua')
        native = NpcData(DATA / 'client', CLIENT_SHA, enum_sha)
        policy = json.loads((DATA / 'formal_npc_hp.json').read_bytes())
        count = 0
        for key, row in policy['templates'].items():
            item = row.get('current_client_component_hp')
            if item is None:
                continue
            definition = native.npc(int(key))
            self.assertEqual(item['enum'], definition['enum'])
            self.assertEqual(item['script'], (definition['script'] or '').lower())
            self.assertEqual(row['fixed'], item['MAX_HP'])
            self.assertGreater(item['MAX_HP'], 0)
            count += 1
        self.assertEqual(count, 60)


@unittest.skipUnless((DATA / 'client/catalog.sqlite3').is_file(), 'version-locked runtime catalog required')
class RuntimeHPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from els_server.domain.dungeon_routes import route_catalog
        cls.catalog = route_catalog()

    def run_for(self, identity):
        from els_server.domain.dungeon_routes import DungeonRun
        return DungeonRun(identity, str(uuid.UUID(int=528)))

    def test_tree_hp_is_resolved_base_hp_without_extra_gauge_multiplier(self):
        from els_server.domain.formal_npc_hp import maximum
        for template, expected in ((5, 38709), (201, 4608), (618, 4608), (206, 11059)):
            self.assertEqual(maximum(self.catalog, template, dungeon=30000, npc_level=2), local(30000, expected))

    def test_three_ignia_friendly_sources_do_not_override_unbound_dynamics(self):
        from els_server.domain import formal_npc_hp as hp
        run = self.run_for(33302)
        for stage in range(3):
            run._load_stage(stage)
            actors = [n for part in run.parts.values() for n in part['npcs'] if n['template'] == 1897]
            self.assertEqual(len(actors), 1)
            actor = actors[0]
            self.assertTrue(actor['ally'])
            self.assertEqual(actor['team'], 0)
            self.assertEqual(actor['hp'], local(33302, 204798720.0))
            self.assertEqual(hp.initialized_maximum(run, actor), actor['hp'])
            self.assertEqual(struct.unpack_from('>f', attributes(actor['init']), 4)[0], actor['hp'])
            self.assertEqual(hp.summoned_maximum(run, 1897), (local(33302, 101575.703125), 83))
            self.assertIsNone(hp.public_maximum(self.catalog, 1897, 33302, 83))
            context = hp.initialized_source_context(run, actor)
            with self.assertRaises(ValueError):
                hp.source_public_maximum(self.catalog, 1897, 33302, 83, (33302, '0' * 64, *context[2:]))

    def test_12321_uses_only_the_existing_third_stage_whitelist(self):
        from els_server.domain import formal_npc_hp as hp
        run = self.run_for(35710)
        run._load_stage(2)
        self.assertEqual(hp.summoned_maximum(run, 12321), (local(35710, 1020652480.0), 100))
        self.assertNotIn(12321, [n['template'] for part in run.parts.values() for n in part['npcs']])
        for stage in (0, 1):
            run._load_stage(stage)
            if 12321 not in run.graph['stages'][str(stage)]['allowed_summons']:
                with self.assertRaises(ValueError):
                    hp.summoned_maximum(run, 12321)

    def test_all_new_components_take_precedence_over_public_fallbacks(self):
        from els_server.domain import formal_npc_hp as hp
        for key, row in hp.policy()['templates'].items():
            item = row.get('current_client_component_hp')
            if item is not None:
                self.assertEqual(hp.component_maximum(self.catalog, int(key)), hp.f32(item['MAX_HP']))

    def test_formal_raid_hp_is_not_overwritten_by_old_solo_fallback(self):
        from els_server.domain import formal_npc_hp as hp, dungeon_hp_c1 as c1
        mid = next(mid for mid in c1.MAPS if mid in hp.policy()['raid_maps'])
        context = SimpleNamespace(dungeon=mid, check=lambda run: None)
        self.assertEqual(c1._Context.source_hp(context, SimpleNamespace(), 0, 0, -1, {}, 987654.0), 987654.0)

    def test_hero_wire_base_hp_and_once_only_authority_with_instance_metadata(self):
        from els_server.domain import formal_npc_hp as hp, native_hero_inputs as hero
        from els_server.protocol.dungeon_messages import dungeon_start
        run = self.run_for(120000)
        combat = noncombat = 0
        for stage in sorted(map(int, run.graph['stages'])):
            run._load_stage(stage)
            payload = run.population_event().payload
            offset = 12 + sum(12 + sum(len(n['wire']) for n in part['npcs']) for part in run.parts.values())
            count = struct.unpack_from('>I', payload, offset)[0]
            keys = []
            for index in range(count):
                key, *ability = struct.unpack_from('>i4b', payload, offset + 4 + 8 * index)
                self.assertEqual(ability, [0, 0, 0, 0])
                keys.append(key)
            found = []
            for part, body in run.parts.items():
                for actor in body['npcs']:
                    context = (120000, run.graph['source_sha256'], 87, stage, part, -1, actor['source_index'])
                    base = hp.maximum(self.catalog, actor['template'], dungeon=120000, npc_level=87,
                                      boss=actor['boss'], source_context=context)
                    self.assertEqual(struct.unpack_from('>f', attributes(actor['init']), 4)[0], base)
                    authority, selected = hero.source_maximum(self.catalog, actor['template'], base, context)
                    self.assertEqual(actor['hp'], authority)
                    if selected:
                        self.assertEqual(authority, hp.f32(hp.f32(base) * 10))
                        found.append(actor['key'])
                        combat += 1
                        with self.assertRaises(ValueError):
                            hero.source_maximum(self.catalog, actor['template'], base, (120000, '0' * 64, *context[2:]))
                    else:
                        self.assertEqual(authority, base)
                        noncombat += 1
            self.assertEqual(keys, found)
            run._load_stage(stage)
            self.assertEqual(run.population_event().payload, payload)
        self.assertEqual((combat, noncombat), (58, 36))
        self.assertEqual(hero.factor_vector(120000), struct.pack('>I10f', 1, .4, .5, .4, .4, 12, 2, 10, 2.5, 75, 5.3))
        # Empty-member codec fixture only; this does not represent a full actor packet.
        with patch('els_server.protocol.dungeon_messages.member', return_value=b''):
            self.assertEqual(dungeon_start(dungeon_id=120000).payload[-48:-4], hero.factor_vector(120000))
        self.assertEqual(hero.factor_vector(120010), bytes(4))

    def test_boss_raw_inputs_leave_hp_and_damage_reduction_bytes_untouched(self):
        from els_server.domain import boss_npc_stats as boss
        policy = boss.policy()
        for mid, row in policy['maps'].items():
            if row['kind'] == 'field' or not row['static']:
                continue
            key, entry = next(iter(row['static'].items()))
            stage, part, group, index, template = map(int, key.split(':'))
            seed = bytearray.fromhex(self.catalog._data['attribute_seed'])
            before = bytes(seed)
            self.assertTrue(boss.apply(self.catalog, template, seed,
                                      (int(mid), row['graph_sha256'], entry['npc_level'], stage, part, group, index)))
            self.assertEqual(seed[:8], before[:8])
            self.assertEqual(seed[24:52], before[24:52])
            self.assertEqual(seed[76:], before[76:])
            self.assertEqual(list(struct.unpack_from('<6i', seed, 52)), entry['six_resistances'])
            break
        else:
            self.fail('No qualified static Boss input')


if __name__ == '__main__':
    unittest.main()
