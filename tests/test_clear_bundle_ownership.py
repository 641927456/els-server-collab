"""Pin the clear-reward ownership boundary around the equipment loot family.

Two mechanisms can hand out the 118445 clear bundle: pve_economy_flow.clear()
for maps that have their own pve economy rule, and dungeon_equipment_loot_flow
.clear_rewards() for the rest of MAPS. They must never both fire, and a map
must never be silently moved from one to the other.
"""
import unittest
import uuid

from els_server.domain import dungeon_equipment_loot_flow as loot_flow
from els_server.domain import dungeon_equipment_loot_rules as equipment
from els_server.domain import pve_economy_flow

# The two maps that own a pve economy rule; they take that path, which appends
# the bundle itself while reward_transaction is held.
PVE_OWNED = frozenset((35340, 35360))
# The rest of MAPS reach the bundle through clear_rewards().
LOOT_OWNED = frozenset(equipment.MAPS) - PVE_OWNED


class _Store:
    path = None  # never opened: these cases only exercise the dispatch gate
    uid = 1002


class _Account:
    uid = 1002
    account_id = 1
    store = _Store()
    reward_store = None


class _Run:
    def __init__(self, identity):
        self.identity = identity
        self.stage = 0
        self.part = 0
        self.visits = 1
        self.graph = {'source_sha256': '0' * 64}
        self.defeated = {}


class _Session:
    """Just enough surface for enabled(); no application means current_lease."""

    def __init__(self, identity):
        self.dungeon_run = _Run(identity)
        self.phase = 'dungeon_active'
        self.dungeon_substage_synced = True
        self.reward_test = True
        self.item_test = True
        self.drop_probe = True
        self.reward_run_id = str(uuid.uuid4())
        self.account = _Account()
        self.dungeon_participants = (1002,)


class ClearBundleOwnershipTests(unittest.TestCase):
    def test_every_map_is_owned_by_exactly_one_mechanism(self):
        self.assertEqual(PVE_OWNED | LOOT_OWNED, frozenset(equipment.MAPS))
        self.assertFalse(PVE_OWNED & LOOT_OWNED)
        # The partition is decided by the pve economy catalog, not by hand.
        for identity in equipment.MAPS:
            owned = pve_economy_flow.rules.definition(identity) is not None
            self.assertEqual(owned, identity in PVE_OWNED, identity)

    def test_loot_owned_maps_pass_the_dispatch_gate(self):
        for identity in sorted(LOOT_OWNED):
            self.assertTrue(loot_flow.enabled(_Session(identity)), identity)

    def test_a_held_reward_transaction_disables_the_loot_path(self):
        """This is what stops the bundle being granted twice.

        pve_economy_flow.clear() sets reward_transaction on the shadow session
        before dispatching, so clear_rewards() stands down for PVE_OWNED maps.
        """
        for identity in sorted(PVE_OWNED):
            session = _Session(identity)
            self.assertTrue(loot_flow.enabled(session), identity)
            session.reward_transaction = object()
            self.assertFalse(loot_flow.enabled(session), identity)

    def test_clear_rewards_declines_outside_the_family(self):
        # 30000 is an admitted route but not an equipment loot map; the default
        # fixed reward must keep owning its clear.
        self.assertNotIn(30000, equipment.MAPS)
        self.assertIsNone(loot_flow.clear_rewards(_Session(30000), {}))

    def test_the_bundle_quantity_is_the_same_on_both_paths(self):
        values = equipment.catalog()['values']
        self.assertEqual(values['fragment_on_validated_clear'], 50)
        # clear_rewards() builds its plan from catalog()['values'] directly, so
        # the two paths cannot drift apart without changing this number.
        plan = equipment.inventory_plan(values['circuit_fragment_template'],
                                        values['fragment_on_validated_clear'])
        self.assertEqual((plan['template'], plan['quantity']), (118445, 50))


if __name__ == '__main__':
    unittest.main()
