"""Character customization catalog decoded from CharCustomData.

Evidence: analysis/client-6c6b5180/20261014-210735/catalog-resources/CharCustomData.tables.json
(11 native data blocks) with UNIT_TYPE / UNIT_CLASS / CUSTOMIZING_* resolved through
Enum.tables.json.

Customization is cosmetic only: no entry in the native table carries a stat field.
These assertions pin the three-hop chain (item -> CUSTOM_ID -> slot) and the
commerce / scope relations. They must not be read as an activation test: the
server still implements no registration, selection or expiry.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from els_server.domain import character_customization
from els_server.game_data import CLIENT_SHA

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data/character_customizations.json'


class Payload(unittest.TestCase):
    def setUp(self):
        character_customization._payload.cache_clear()
        self.payload = json.loads(DATA.read_text(encoding='utf8'))

    def test_payload_pins_the_current_client(self):
        self.assertEqual(self.payload['client_sha256'], CLIENT_SHA)
        self.assertEqual(self.payload['schema_version'], 1)
        self.assertEqual(self.payload['policy'], 'character-customization-catalog-only-v1')

    def test_ten_blocks_cover_every_populated_slot(self):
        blocks = self.payload['blocks']
        self.assertEqual(set(blocks), {
            'face', 'wait_motion', 'sit_motion', 'skill_cutin', 'hyper_effect',
            'skill_frame', 'portrait', 'quick_voice', 'emoticon', 'point_mark'})
        self.assertEqual(sum(b['entry_count'] for b in blocks.values()), 6615)

    def test_every_block_declares_native_slot_types(self):
        types = self.payload['enum_authority']['CUSTOMIZING_TYPE']
        for label, block in self.payload['blocks'].items():
            self.assertTrue(block['customizing_types'], '%s has no slot type' % label)
            for name in block['customizing_types']:
                self.assertIn(name, types, '%s declares unknown slot %s' % (label, name))

    def test_multi_slot_families_are_not_collapsed(self):
        blocks = self.payload['blocks']
        self.assertEqual(len(blocks['quick_voice']['customizing_types']), 4)
        self.assertEqual(len(blocks['emoticon']['customizing_types']), 4)
        self.assertEqual(len(blocks['skill_cutin']['customizing_types']), 4)
        self.assertIn('CT_SIT_MOTION_OPTION', blocks['sit_motion']['customizing_types'])

    def test_no_entry_carries_a_stat_field(self):
        forbidden = {'STAT', 'm_fAtkPhysic', 'm_fAtkMagic', 'm_fDefPhysic', 'm_fDefMagic'}
        for label, block in self.payload['blocks'].items():
            for entry in block['entries']:
                self.assertEqual(forbidden & set(entry), set(),
                                 '%s entry carries a stat field' % label)


class Chain(unittest.TestCase):
    def setUp(self):
        character_customization._payload.cache_clear()

    def test_portrait_item_resolves_to_a_custom_id(self):
        self.assertEqual(character_customization.granted_by(470532),
                         [{'block': 'portrait', 'custom_id': 15001}])
        entry = character_customization.entry('portrait', 15001)
        self.assertEqual(entry['ITEM_ID'], 470532)
        self.assertEqual(entry['UNIT_TYPE'], 1)
        self.assertIs(entry['IS_SALE'], False)  # sold as an item, not in the slot list

    def test_quick_voice_entry_carries_a_play_type(self):
        entry = character_customization.entry('quick_voice', 16001)
        self.assertEqual(entry['ITEM_ID'], 470705)
        self.assertIn('SOUND_PLAY_TYPE', entry)

    def test_unknown_lookups_are_empty_not_errors(self):
        self.assertIsNone(character_customization.entry('portrait', 99999999))
        self.assertEqual(character_customization.granted_by(1), [])
        self.assertEqual(character_customization.replace_targets(99999999), [])
        self.assertIsNone(character_customization.period_hours(1))

    def test_unknown_block_is_rejected(self):
        with self.assertRaises(ValueError):
            character_customization.entries('haircut')


class Commerce(unittest.TestCase):
    def setUp(self):
        character_customization._payload.cache_clear()

    def test_on_sale_entries_are_boolean_not_string(self):
        entry = character_customization.entry('face', 12001)
        self.assertIs(entry['IS_SALE'], True)

    def test_timed_items_record_hours_not_days(self):
        # 164550 is 温泉坐姿：艾索德（7日）; 168 hours is the 7-day period.
        self.assertEqual(character_customization.period_hours(164550), 168)
        self.assertEqual(len(character_customization._payload()['period_items']), 285)

    def test_one_public_registration_is_account_visible(self):
        public = character_customization._payload()['public_registrations']
        self.assertEqual(public, [{'data_type': 19, 'item_id': 718716}])

    def test_point_mark_is_account_scoped(self):
        self.assertTrue(character_customization.is_account_scoped(18000))
        self.assertFalse(character_customization.is_account_scoped(15001))


class Relations(unittest.TestCase):
    def setUp(self):
        character_customization._payload.cache_clear()

    def test_replace_relations_are_pairs_per_base_custom_id(self):
        self.assertEqual(character_customization.replace_targets(101003), [101015, 101016])
        self.assertEqual(len(character_customization._payload()['replace_map']), 69)

    def test_socket_groups_expose_the_allowed_socket_list(self):
        sockets = character_customization._payload()['item_sockets']
        self.assertEqual(len(sockets), 2)
        self.assertEqual(sockets[0]['group_id'], 0)
        self.assertIn(215101, sockets[0]['socket_ids'])


if __name__ == '__main__':
    unittest.main()
