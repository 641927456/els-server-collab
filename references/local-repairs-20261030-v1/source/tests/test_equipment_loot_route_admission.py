"""Pin the four chip routes wired into the finite equipment loot catalog.

Adding a map to MAPS lets the running server hand a player an item after a Boss
dies, so each admission needs its own evidence: the route is admitted, it is not
raid-managed (raid economy would double-grant), its native definition declares
the template, and the stored graph/definition digests still match live data.
"""
import hashlib
import unittest
import uuid

from els_server.domain import dungeon_equipment_loot_rules as equipment
from els_server.domain.dungeon_routes import route_catalog
from els_server.domain.raid_economy_flow import rules as raid_rules
from els_server.game_data import client_data

NEW_MAPS = (35450, 35460, 35470, 35480)
CHIP = 118638


def _native_common(identity):
    definition = client_data().dungeon(identity)
    return {v for v in (definition.get('BOSS_DROP_ITEM') or {}).get('COMMON', {}).values()
            if type(v) is int and v > 0}


def _identity(identity):
    routes = route_catalog()._data
    graph = routes['graphs'][routes['routes'][str(identity)]['source']]
    return dict(owner=1002, run_id=str(uuid.uuid4()), dungeon=identity, stage=0, part=0,
                visits=1, npc_key=1, graph_sha256=graph['source_sha256'])


class EquipmentLootRouteAdmissionTests(unittest.TestCase):
    def test_the_admitted_map_set_is_pinned(self):
        self.assertEqual(equipment.MAPS, frozenset((35340, 35360, 35390, 35400, *NEW_MAPS)))

    def test_no_wired_route_is_raid_managed(self):
        # raid_economy_flow.managed() takes a session, so read the same rule
        # definition it reads; passing an int there silently answers False.
        for identity in equipment.MAPS:
            self.assertIsNone(raid_rules.definition(identity), identity)

    def test_every_wired_route_declares_the_template_it_can_drop(self):
        for identity in equipment.MAPS:
            pool = equipment.catalog()['maps'][str(identity)]['finite_boss_candidates']
            for template in pool:
                self.assertIn(template, _native_common(identity), (identity, template))

    def test_stored_route_digests_still_match_live_data(self):
        routes = route_catalog()._data
        catalog = equipment.catalog()
        for identity in NEW_MAPS:
            row = catalog['maps'][str(identity)]
            graph = routes['graphs'][routes['routes'][str(identity)]['source']]
            self.assertEqual(row['dungeon'], identity)
            self.assertEqual(row['graph_source_sha256'], graph['source_sha256'], identity)
            self.assertEqual(row['source_definition_sha256'],
                             hashlib.sha256(client_data()._definition('dungeons', 'id', identity).encode()).hexdigest(),
                             identity)

    def test_a_boss_plan_for_a_new_route_yields_one_chip_with_options(self):
        for identity in NEW_MAPS:
            plans = equipment.plans(_identity(identity), True, randbelow=lambda n: 0)
            self.assertEqual([(p['template'], p['quantity']) for p in plans], [(CHIP, 1)], identity)
            self.assertIsInstance(plans[0]['option_groups'], dict, identity)

    def test_a_wired_route_still_needs_its_own_graph_digest(self):
        identity = _identity(35450)
        identity['graph_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            equipment.context(identity)

    def test_wiring_a_route_also_grants_the_clear_fragment_bundle(self):
        """Wiring a route is not only "Boss may drop a chip".

        A validated solo clear also yields the 118445 bundle. For these four
        maps it comes from dungeon_equipment_loot_flow.clear_rewards(); they
        have no pve_economy rule, so that is the only branch that runs. The
        quantity is pinned here so the player-visible consequence cannot drift
        silently, and the bundle is checked to be issuable before it is
        promised.
        """
        values = equipment.catalog()['values']
        self.assertEqual(values['fragment_on_validated_clear'], 50)
        self.assertEqual(values['circuit_fragment_template'], 118445)
        self.assertEqual(values['boss_extra_item_percent'], 25)
        plan = equipment.inventory_plan(values['circuit_fragment_template'],
                                        values['fragment_on_validated_clear'])
        self.assertEqual((plan['template'], plan['quantity']), (118445, 50))
        for identity in NEW_MAPS:
            self.assertIn(identity, equipment.MAPS)

    def test_an_unwired_neighbour_stays_unadmitted(self):
        # 35440 is raid-managed and 35170 declares no hostile drop at all; both
        # must stay outside this catalog rather than be pulled in by adjacency.
        catalog = equipment.catalog()
        for identity in (35440, 35170):
            self.assertNotIn(identity, equipment.MAPS)
            self.assertNotIn(str(identity), catalog['maps'])


if __name__ == '__main__':
    unittest.main()
