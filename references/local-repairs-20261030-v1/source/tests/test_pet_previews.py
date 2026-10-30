"""Cash-item to companion preview links.

Evidence: analysis/client-6c6b5180/20261014-210735/catalog-resources/
PetPreView.tables.json — 578 AddPetPreViewData registrations.

Two things this file pins, both of which a naive import gets wrong:

  * the target symbol table is not always PET_UNIT_ID. 141 registrations name an
    RPUI_* mount, which only resolves through RIDING_PET_UNIT_ID.
  * an item does not map to one unit. Ten items are random-box pools; the largest
    previews 24 mounts. Keying by item alone keeps the last registration and
    loses 59 links, so each item maps to an ordered list here.

The 7 exact duplicate registrations the client emits are collapsed, and the
summary records that number so the collapse is visible rather than silent.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from els_server.domain import companion_templets, pet_previews
from els_server.game_data import CLIENT_SHA

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data/pet_previews.json'


class PreviewPayload(unittest.TestCase):
    def setUp(self):
        pet_previews._payload.cache_clear()
        pet_previews._by_symbol.cache_clear()
        self.payload = json.loads(DATA.read_text(encoding='utf8'))

    def test_payload_pins_the_current_client(self):
        self.assertEqual(self.payload['client_sha256'], CLIENT_SHA)
        self.assertEqual(self.payload['schema_version'], 1)

    def test_the_link_counts_are_exact(self):
        summary = pet_previews.summary()
        self.assertEqual(summary['pet_previews'], 430)
        self.assertEqual(summary['mount_previews'], 141)
        self.assertEqual(summary['preview_links'], 571)
        self.assertEqual(summary['pet_items'], 411)
        self.assertEqual(summary['mount_items'], 101)
        self.assertEqual(summary['exact_duplicate_registrations_dropped'], 7)

    def test_a_pool_keeps_every_unit_it_previews(self):
        summary = pet_previews.summary()
        self.assertEqual(summary['multi_unit_pools'], 10)
        self.assertEqual(summary['largest_pool'], 24)
        self.assertEqual(len(pet_previews.previews(110004102)), 24)
        self.assertTrue(pet_previews.is_pool(110004102))
        self.assertFalse(pet_previews.is_pool(90002292))

    def test_every_link_resolves_to_a_templet_of_the_right_kind(self):
        pets = companion_templets.catalog('pet')
        mounts = companion_templets.catalog('mount')
        self.assertEqual(pet_previews.summary()['templet_unlinked'], 0)
        for kind, catalog in (('pet', pets), ('mount', mounts)):
            for item_id, rows in (pet_previews.pet_previews() if kind == 'pet'
                                  else pet_previews.mount_previews()).items():
                for row in rows:
                    self.assertIsNotNone(row['templet_key'], item_id)
                    self.assertIn(int(row['templet_key']), catalog, row['symbol'])
                    self.assertIn(row['symbol'].split('_')[0], ('PUI', 'RPUI'))

    def test_mount_symbols_do_not_resolve_against_the_pet_table(self):
        # 141 registrations name RPUI_* units; PET_UNIT_ID has no such entry, so a
        # single-table resolver would have dropped every one of them.
        pet_symbols = set(self.payload['enum_authority']['PET_UNIT_ID'])
        mount_symbols = set(self.payload['enum_authority']['RIDING_PET_UNIT_ID'])
        self.assertEqual(len(pet_symbols), 355)
        self.assertEqual(len(mount_symbols), 143)
        for rows in pet_previews.mount_previews().values():
            for row in rows:
                self.assertNotIn(row['symbol'], pet_symbols)
                self.assertIn(row['symbol'], mount_symbols)
        for rows in pet_previews.pet_previews().values():
            for row in rows:
                self.assertIn(row['symbol'], pet_symbols)

    def test_one_item_can_preview_both_a_pet_and_a_mount(self):
        both = pet_previews.previews(288761)
        self.assertEqual(len(pet_previews.previews(288761, 'pet')), 6)
        self.assertEqual(len(pet_previews.previews(288761, 'mount')), 7)
        self.assertEqual(len(both), 13)
        self.assertEqual(pet_previews.units(288761, 'pet'),
                         tuple(sorted(r['unit_id'] for r in pet_previews.previews(288761, 'pet'))))

    def test_unknown_items_preview_nothing(self):
        self.assertEqual(pet_previews.previews(1), ())
        self.assertEqual(pet_previews.units(1), ())
        self.assertFalse(pet_previews.is_pool(1))
        with self.assertRaises(ValueError):
            pet_previews.previews(1, 'vehicle')

    def test_reverse_lookup_finds_the_shop_item(self):
        hits = pet_previews.items_for('PUI_HALLOWEEN_PUMPKIN_TANYA_F')
        self.assertEqual(hits, ((90002292, 'pet'), (90002296, 'pet')))
        pattern = pet_previews.items_for('RPUI_NO_SUCH_MOUNT')
        self.assertEqual(pattern, ())
        # The prefix-qualified spelling resolves to the same set.
        self.assertEqual(pet_previews.items_for('PET_UNIT_ID.PUI_HALLOWEEN_PUMPKIN_TANYA_F'),
                         hits)

    def test_no_drop_chance_is_claimed(self):
        # A 24-unit pool must not be readable as 24 equal chances.
        forbidden = {'chance', 'probability', 'weight', 'rate', 'percent'}
        stack = [self.payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                self.assertFalse(forbidden & set(node), node.keys())
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        self.assertIn('No drop chance is recorded', ' '.join(self.payload['not_claimed']))


if __name__ == '__main__':
    unittest.main()
