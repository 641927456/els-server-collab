"""Protocol-only checks; these do not claim live profession selection works."""
import json
import unittest
from dataclasses import replace
from els_server.paths import PROJECT_ROOT
from els_server.protocol.profession_messages import (
    ProfessionState, state_wire, select_request, selection_ack, counter_update, level_update)


class ProfessionMessagesTests(unittest.TestCase):
    def test_unselected_state_matches_existing_character_fixture(self):
        fixture = json.loads((PROJECT_ROOT/'analysis/character-fixture.json').read_text())
        field = next(f for f in fixture['fields'] if f['offset'] == '0x3de')
        self.assertEqual(state_wire(ProfessionState()).hex(), field['wire_hex'])
        self.assertEqual(len(state_wire(ProfessionState())), 18)

    def test_scalar_types_and_order_match_native_reader_specification(self):
        # Synthetic markers, not profession progression data. Golden bytes
        # distinguish BE integers from native DTO addresses and float encoding.
        state = ProfessionState(3, 7, 0x12345678, {2: -1, -1: 0x1020304}, 17, 255)
        self.assertEqual(state_wire(state).hex(),
            '03071234567800000002ffffffff0102030400000002ffffffff00000011000000ff')
        ack = selection_ack(-2, state, {9: 1.5, -2: -2.25}, tail_u64=0x102030405060708,
                            tail_i32=-3, tail_flag_a=True, tail_flag_b=False)
        self.assertEqual(ack.hex(),
            'fffffffe03071234567800000002ffffffff0102030400000002ffffffff00000011000000ff'
            '00000002fffffffec0100000000000093fc000000102030405060708fffffffd0100')
        self.assertEqual(len(ack), 40+8*4)

    def test_request_rejects_invalid_types_and_trailing_fields(self):
        for selected in (1, 2, 3):
            self.assertEqual(select_request(bytes([selected])), selected)
        for wire in (b'', b'\0', b'\4', b'\xff', b'\1\0', bytearray(b'\1'), None):
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                select_request(wire)

    def test_counter_delta_matches_native_integer_map(self):
        self.assertEqual(counter_update({}), b'\0\0\0\0')
        self.assertEqual(counter_update({3: -7, 1: 0}).hex(),
                         '00000002000000010000000000000003fffffff9')
        for values in ({True: 1}, {1: 1.5}, {1: 2**31}, {-(2**31)-1: 0},
                       [], {i: 0 for i in range(513)}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                counter_update(values)

    def test_level_notification_uid_and_effect_map_layout(self):
        self.assertEqual(level_update(1001, ProfessionState(2, 2, 45, {}, 5, 80), {7: 2.25}).hex(),
                         '00000000000003e902020000002d000000000000000500000050'
                         '000000010000000740100000')
        for uid in (0, -1, True, 1.0, 2**63):
            with self.subTest(uid=uid), self.assertRaises(ValueError):
                level_update(uid, ProfessionState(), {})
        with self.assertRaises(ValueError):
            level_update(1001, ProfessionState(), {1: float('nan')})

    def test_untrusted_values_cannot_overflow_or_change_shape(self):
        for field, value in [('profession', 4), ('profession', True), ('level', 256),
                             ('experience', -1), ('progress', 2**31), ('required', 1.0),
                             ('counters', {True: 1}), ('counters', {1: 2**31}),
                             ('counters', {i: 0 for i in range(513)}), ('counters', [])]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                state_wire(replace(ProfessionState(), **{field: value}))
        for values in ({1: float('nan')}, {1: float('inf')}, {1: 1e40}, {1: True}, {1: 10**1000}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                selection_ack(0, ProfessionState(), values, tail_u64=0, tail_i32=0,
                              tail_flag_a=False, tail_flag_b=False)
        with self.assertRaises(ValueError):
            selection_ack(0, ProfessionState(), {}, tail_u64=-1, tail_i32=0,
                          tail_flag_a=False, tail_flag_b=False)
        with self.assertRaises(ValueError):
            selection_ack(0, ProfessionState(), {}, tail_u64=0, tail_i32=0,
                          tail_flag_a=1, tail_flag_b=False)
