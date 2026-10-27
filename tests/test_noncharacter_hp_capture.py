import struct
from types import SimpleNamespace
import unittest
from els_server.domain.local_session import LocalSession,LocalAccount


class NoncharacterCaptureTests(unittest.TestCase):
    def test_legacy_without_character_clears_old_luciel_capture(self):
        session=LocalSession(LocalAccount())
        session.luciel_dungeon_hp_source='old';session.luciel_dungeon_hp_max=123
        session._capture_luciel_dungeon_hp(b'',{})
        self.assertIsNone(session.luciel_dungeon_hp_source)
        self.assertIsNone(session.luciel_dungeon_hp_max)

    def test_missing_owned_projection_fails_closed(self):
        session=LocalSession(LocalAccount())
        session.account=SimpleNamespace(characters=object(),character=lambda:None)
        with self.assertRaisesRegex(ValueError,'Missing owned character'):
            session._capture_luciel_dungeon_hp(b'',{})

    def test_real_luciel_keeps_strict_spans_and_native_float(self):
        session=LocalSession(LocalAccount())
        session.account=SimpleNamespace(uid=1001,characters=object(),character=lambda:{'unit_type':10})
        with self.assertRaisesRegex(ValueError,'member spans'):
            session._capture_luciel_dungeon_hp(b'',{})
        spans={'0x198':(0,4),'0x1b4':(4,8),'0x1d1':(8,12)}
        payload=struct.pack('>fff',123.5,10,20)
        session._capture_luciel_dungeon_hp(payload,spans)
        self.assertEqual(session.luciel_dungeon_hp_source,(1001,payload,spans))
        self.assertEqual(session.luciel_dungeon_hp_max,123.5)


if __name__=='__main__':unittest.main()
