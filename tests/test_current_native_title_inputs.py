"""Current titles change only their existing native snapshot fields."""
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = all((ROOT / p).is_file() for p in (
    'els_server/data/client/catalog.sqlite3',
    'analysis/character-fixture.json',
    'analysis/dungeon-member-fixture.json',
))


@unittest.skipUnless(ASSETS, 'version-locked native DTO fixtures required')
class CurrentNativeTitleInputsTests(unittest.TestCase):
    def character(self, unit_type):
        from els_server.storage.characters import BASE_CLASSES
        # This synthetic role belongs to the locked fixture's account1.
        # Real runtime projections provide the verified SQL owner explicitly.
        return dict(uid=1001, account_id=1, name='TitleFixture', unit_type=unit_type,
                    unit_class=BASE_CLASSES[unit_type], level=99,
                    transcendence=False, master=False)

    def encoders(self):
        from els_server.domain.character_rules import default_slots
        from els_server.protocol import local_messages, dungeon_messages
        return (
            lambda c: local_messages.character_unit(character=c, items=[]),
            lambda c: dungeon_messages.member(default_slots(c), c, []),
        )

    def test_owned_snapshot_changes_only_the_current_title_field(self):
        from els_server.domain.titles import eligible
        for unit_type in (1, 5, 14):
            character = self.character(unit_type)
            self.assertTrue(eligible(character, 13330))
            for encode in self.encoders():
                with self.subTest(unit_type=unit_type, encode=encode):
                    baseline = encode(character)
                    self.assertEqual(baseline, encode(dict(character, title=0)))
                    titled = encode(dict(character, title=13330))
                    needle = struct.pack('>i', 13330)
                    self.assertEqual(titled.count(needle), 1)
                    offset = titled.index(needle)
                    self.assertEqual(baseline[offset:offset + 4], bytes(4))
                    self.assertEqual(titled, baseline[:offset] + needle + baseline[offset + 4:])
                    self.assertNotIn('title', character)

    def test_malformed_or_unknown_titles_are_rejected_by_both_snapshots(self):
        for title in (True, -1, 1.0, '13330', 2147483647):
            for encode in self.encoders():
                with self.subTest(title=title, encode=encode):
                    with self.assertRaises(ValueError):
                        encode(dict(self.character(1), title=title))


if __name__ == '__main__':
    unittest.main()
