"""The whole native client symbol table, imported once.

Evidence: analysis/client-6c6b5180/resource-scripts/Enum.tables.json, 747 named
tables and 29 flat constants, 36,578 literals.

This file is the symbol authority the two earlier imports had to work around: the
companion templets pinned three hand-picked tables and the character
customisations pinned two. Those slices are now checked against the full table
here, so a disagreement between the hand-picked copy and the client fails loudly
instead of drifting.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from els_server.domain import enums
from els_server.game_data import CLIENT_SHA

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data/enums.json'


class EnumPayload(unittest.TestCase):
    def setUp(self):
        enums._payload.cache_clear()
        enums._reverse.cache_clear()
        self.payload = json.loads(DATA.read_text(encoding='utf8'))

    def test_payload_pins_the_current_client(self):
        self.assertEqual(self.payload['client_sha256'], CLIENT_SHA)
        self.assertEqual(self.payload['schema_version'], 1)

    def test_the_whole_table_is_present(self):
        summary = enums.summary()
        self.assertEqual(summary['constants'], 29)
        self.assertEqual(summary['tables'], 718)
        self.assertEqual(summary['constants'] + summary['tables'], 747)
        self.assertEqual(summary['literals'], 36578)
        self.assertEqual(len(enums.table_names()), 718)

    def test_every_literal_is_an_integer(self):
        for name, body in enums.tables().items():
            for symbol, number in body.items():
                self.assertIsInstance(number, int, '%s.%s' % (name, symbol))
        for name, number in enums.constants().items():
            self.assertIsInstance(number, int, name)

    def test_the_end_sentinels_are_not_given_an_invented_number(self):
        sentinels = enums.opaque()
        self.assertEqual(sum(len(body) for body in sentinels.values()), 11)
        for name, body in sentinels.items():
            for slot, value in body.items():
                self.assertNotIsInstance(value, int, '%s.%s' % (name, slot))
                self.assertEqual(list(value), ['global'])
                self.assertFalse(value['global'] in enums.table(name))

    def test_lookup_accepts_a_qualified_symbol(self):
        self.assertEqual(enums.lookup('PET_UNIT_ID.PUI_TEST'), 1)
        self.assertEqual(enums.lookup('UNIT_TYPE.UT_ELSWORD'), 1)
        self.assertEqual(enums.lookup('CUSTOMIZING_TYPE.CT_PORTRAIT'), 19)

    def test_lookup_accepts_a_bare_flat_constant(self):
        self.assertEqual(enums.lookup('TRUE'), 1)
        self.assertEqual(enums.lookup('FALSE'), 0)

    def test_lookup_refuses_an_ambiguous_bare_symbol(self):
        # SGI_END lives inside SERVER_GROUP_ID as a sentinel, not as a constant;
        # a bare lookup must not silently search every table for it.
        with self.assertRaises(KeyError):
            enums.lookup('SGI_END')

    def test_unknown_tables_and_symbols_raise(self):
        with self.assertRaises(ValueError):
            enums.table('NO_SUCH_TABLE')
        with self.assertRaises(KeyError):
            enums.value('PET_UNIT_ID', 'PUI_NO_SUCH_PET')
        with self.assertRaises(ValueError):
            enums.lookup('')

    def test_the_five_largest_tables_are_the_ones_we_expect(self):
        sizes = {entry['table']: entry['entries']
                 for entry in enums.summary()['largest_tables']}
        self.assertEqual(sizes['NPC_UNIT_ID'], 7692)
        self.assertEqual(sizes['SKILL_ID'], 4909)
        self.assertEqual(sizes['BUFF_TEMPLET_ID'], 3425)
        self.assertEqual(len(enums.table('NPC_UNIT_ID')), 7692)

    def test_reverse_returns_every_alias_not_just_one(self):
        # Eight tables reuse a number for more than one symbol; the client really
        # does that, so reverse lookup has to keep the whole set.
        with_aliases = [name for name in enums.table_names() if enums.aliases(name)]
        self.assertEqual(len(with_aliases), 8)
        self.assertIn('INVENTORY_POPUP_STATE_TYPE', with_aliases)
        for name in with_aliases:
            for number, symbols in enums.aliases(name).items():
                self.assertGreater(len(symbols), 1, name)
                self.assertEqual(enums.reverse(name, number), symbols)
                for symbol in symbols:
                    self.assertEqual(enums.value(name, symbol), number)

    def test_a_table_without_aliases_reports_none(self):
        self.assertEqual(enums.aliases('ITEM_TYPE'), {})
        number = enums.value('ITEM_TYPE', 'IT_END')
        self.assertEqual(len(enums.reverse('ITEM_TYPE', number)), 1)


class EnumAgreesWithTheHandPickedSlices(unittest.TestCase):
    """The two earlier imports pinned symbol slices by hand. Prove they match."""

    def setUp(self):
        enums._payload.cache_clear()

    def test_character_customisation_slice_matches(self):
        payload = json.loads(
            (ROOT / 'els_server/data/character_customizations.json').read_text(encoding='utf8'))
        for table_name, slice_ in payload['enum_authority'].items():
            self.assertEqual(enums.table(table_name), slice_, table_name)

    def test_companion_templet_slice_matches(self):
        # The templet file records table *sizes* rather than values.
        payload = json.loads(
            (ROOT / 'els_server/data/companion_templets.json').read_text(encoding='utf8'))
        for table_name, size in payload['enum_authority'].items():
            self.assertEqual(len(enums.table(table_name)), size, table_name)

    def test_preview_and_transcendental_slices_match(self):
        for name in ('pet_previews', 'transcendental_class_items'):
            payload = json.loads(
                (ROOT / ('els_server/data/%s.json' % name)).read_text(encoding='utf8'))
            for table_name, slice_ in payload['enum_authority'].items():
                full = enums.table(table_name)
                for symbol, number in slice_.items():
                    self.assertIn(symbol, full, '%s.%s' % (table_name, symbol))
                    self.assertEqual(full[symbol], number, '%s.%s' % (table_name, symbol))
                if table_name in ('PET_UNIT_ID', 'RIDING_PET_UNIT_ID'):
                    # These two are pinned whole, so the sizes must agree too.
                    # UNIT_TYPE is pinned narrow on purpose: the transcendental
                    # table registers 15 of the 17 client types.
                    self.assertEqual(len(full), len(slice_), table_name)


if __name__ == '__main__':
    unittest.main()
