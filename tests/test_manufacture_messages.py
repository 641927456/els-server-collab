"""Boundary checks for crafting codecs; not live crafting acceptance."""
import json
import struct
import unittest
from dataclasses import asdict
from els_server.paths import PROJECT_ROOT
from els_server.protocol.manufacture_messages import manufacture_request, manufacture_ack


class ManufactureMessagesTests(unittest.TestCase):
    def test_original_auxiliary_set_to_wire_chain(self):
        proof=json.loads((PROJECT_ROOT/'analysis/integration-20261015/manufacture-auxiliary-native.json').read_text())
        for row in proof['cases']:
            wire=bytes.fromhex(row['wire_hex'])
            with self.subTest(entries=row['entries']):
                if not row['server_accepted']:
                    with self.assertRaises(ValueError):manufacture_request(wire)
                    continue
                request=manufacture_request(wire)
                self.assertEqual(request.auxiliary_uids,tuple(row['auxiliary']))
                self.assertEqual(request.selected_uid,row['selected_uid'])
                self.assertEqual((request.recipe_id,request.quantity),(30445,7))

    def test_original_writer_captures_roundtrip(self):
        proof = json.loads((PROJECT_ROOT/'analysis/integration-20261015/manufacture-native-protocol.json').read_text())
        for row in proof['requests']:
            result = asdict(manufacture_request(bytes.fromhex(row['wire_hex'])))
            result['auxiliary_uids'] = list(result['auxiliary_uids'])
            self.assertEqual(result, row['parsed'])

    def test_request_size_and_uid_set_rejection(self):
        good = struct.pack('>iiqI', 30445, 1, -1, 0)
        bad = [good[:i] for i in range(len(good))] + [good+b'\0', None, bytearray(good)]
        bad += [struct.pack('>iiqI', r, n, selected, 0)
                for r, n, selected in [(0, 1, -1), (1, 0, -1), (1, -1, -1),
                                        (1, 1, 0), (1, 1, -2)]]
        for uids in [(2, 1), (1, 1), (0,), (-1,), tuple(range(1, 7))]:
            bad.append(struct.pack('>iiqI', 30445, 1, -1, len(uids))
                       + struct.pack('>'+'q'*len(uids), *uids))
        bad.append(struct.pack('>iiqIq', 30445, 1, 77, 1, 77))
        for wire in bad:
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                manufacture_request(wire)

    def test_ack_explicit_fields_and_empty_shape(self):
        fields = dict(result=0, rewards={}, changes=[], ed=0x102030405060708,
                      profession_xp=17, limit_id=10130467, limit_value=29)
        wire = manufacture_ack(**fields)
        self.assertEqual(len(wire), 32)
        self.assertEqual(wire, struct.pack('>iIQIiii', 0, 0, fields['ed'], 0, 17, 10130467, 29))
        for key, value in [('result', True), ('ed', -1), ('ed', 2**63),
                           ('profession_xp', 2**31), ('limit_id', -1),
                           ('limit_value', 1.5), ('rewards', {1:0}),
                           ('rewards', {True:1}), ('rewards', {1:2**31}),
                           ('changes', [((27, 0), None)]*2)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                manufacture_ack(**{**fields, key:value})
        with self.assertRaises(ValueError):
            manufacture_ack(**{**fields, 'changes':[((27, 1),
                dict(uid=1, template=81021, metadata=0, count=1, group=27, slot=0))]})
