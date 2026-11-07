"""Sage-stone re-skins share one pinned outcome table.

135793 (扭曲的贤者的魔法石) and 710085 ([阿莉尔]贤者的魔法石) are re-skins of
135184: their record[0x98:0xa0] per-item data offset is byte-identical, so the
same outcome weights and fee grade apply and the stone must not be rejected as
an unsupported material. The [特级] family (154039/154042/...) lives in its own
data block and must never be aliased.

The alias map was dropped when the accepted release profile replaced
els_server/storage/sage_sockets.py (audit P1-1: the profile pins that file's
bytes, so accepting an alias there needs a new candidate source set). The
evidence checks stay here and skip while the map is absent, so re-enabling it
is a one-line change that this module verifies.
"""
import unittest

from els_server.domain import sage_sockets as sage
from els_server.game_data import client_data

ALIASES = (135793, 710085)
SPECIAL_STONES = (154039, 154042)
TARGET = {'template': 11006011, 'enhancement': 0, 'option_groups': {}}


def definition(template):
    return client_data().item(template)


def data_block(template):
    """Per-item data offset: equal bytes mean one shared effect table."""
    return definition(template)['record'][0x98:0xa0]


class SageStoneEvidenceTests(unittest.TestCase):
    """Always runs: the client evidence behind any future alias map."""

    def test_alias_records_share_the_sage_data_block(self):
        for template in ALIASES:
            self.assertEqual(data_block(template), data_block(sage.STONE),
                             f'{template} no longer shares the sage data block')

    def test_alias_records_match_the_sage_classification(self):
        base = definition(sage.STONE)
        for template in ALIASES:
            item = definition(template)
            self.assertEqual((item['metadata'], item['item_type'], (item['flags4'] >> 20) & 15),
                             (base['metadata'], base['item_type'], (base['flags4'] >> 20) & 15))

    def test_special_stones_keep_their_own_data_block(self):
        for template in SPECIAL_STONES:
            self.assertNotEqual(data_block(template), data_block(sage.STONE))


@unittest.skipUnless(hasattr(sage, 'STONE_ALIASES'),
                     'alias map is not in the accepted runtime (audit P1-1)')
class SageStoneAliasTests(unittest.TestCase):
    def test_alias_map_covers_exactly_the_reskins(self):
        self.assertEqual(dict(sage.STONE_ALIASES), {135793: sage.STONE, 710085: sage.STONE})

    def test_alias_rolls_the_same_outcomes_as_the_sage_stone(self):
        base = sage.distribution(TARGET, sage.STONE)
        for template in ALIASES:
            self.assertEqual(sage.distribution(TARGET, template), base)

    def test_alias_pays_the_sage_fee(self):
        base = sage.fee(TARGET, sage.STONE)
        for template in ALIASES:
            self.assertEqual(sage.fee(TARGET, template), base)

    def test_special_stones_stay_out_of_the_alias_map(self):
        for template in SPECIAL_STONES:
            self.assertNotIn(template, sage.STONE_ALIASES)


if __name__ == '__main__':
    unittest.main()
