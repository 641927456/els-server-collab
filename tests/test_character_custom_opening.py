"""Exercise the original menu's wire envelope without private game assets."""
import dataclasses
import sys
import types
import unittest
from unittest.mock import Mock, patch

from els_server.domain import character_custom
from els_server.protocol.protocol_codec import (
    BOOTSTRAP_KEYS, Event, decode_event, decode_frame, encode_event, encode_frame,
)


class CharacterCustomOpeningTests(unittest.TestCase):
    def setUp(self):
        self.session = types.SimpleNamespace(account=types.SimpleNamespace(
            uid=1001, account_id=17, store=types.SimpleNamespace(path='unused.sqlite3')))
        self.request = Event(0x202, kind=0x634, performers=(0,))
        self.response = Event(0x201, kind=0x635, payload=bytes(8))
        self.opening = Mock(return_value=[self.response])
        self.context = Mock(return_value=object())
        self.admitted = self.enterContext(patch.object(character_custom, 'admitted', return_value=True))
        self.enterContext(patch.dict(sys.modules, {
            'els_server.storage.character_custom': types.SimpleNamespace(opening_info=self.opening),
            'els_server.domain.avatar_set_flow': types.SimpleNamespace(
                context=self.context, validate=Mock()),
        }))

    def test_native_menu_frame_reaches_opening_information(self):
        # 23ACF70 -> 7E9610 -> 683650 constructs a single zero performer.
        # An empty performer fixture produces a different (64-byte) frame.
        frame = encode_frame(encode_event(self.request), BOOTSTRAP_KEYS)
        self.assertEqual(len(frame), 72)
        event = decode_event(decode_frame(frame, BOOTSTRAP_KEYS).plaintext)
        self.assertEqual(character_custom.handle(self.session, event, 1), [self.response])
        self.opening.assert_called_once()
        self.assertEqual(self.opening.call_args.args, ('unused.sqlite3', 1001, 17))
        self.assertTrue(callable(self.opening.call_args.kwargs['validate']))

    def test_malformed_envelopes_never_reach_storage(self):
        for changes in (
            {'performers': ()}, {'performers': (1,)}, {'performers': (0, 0)},
            {'uid': 1001}, {'target_uid': 1001}, {'payload': b'\x00'},
            {'payload_mode': 1}, {'event_id': 0x201},
        ):
            with self.subTest(changes=changes):
                event = dataclasses.replace(self.request, **changes)
                self.assertEqual(character_custom.handle(self.session, event, 1), [])
        for sequence in (0, 2**32, True):
            with self.subTest(sequence=sequence):
                self.assertEqual(character_custom.handle(self.session, self.request, sequence), [])
        self.opening.assert_not_called()

    def test_session_admission_still_required(self):
        self.admitted.return_value = False
        self.assertEqual(character_custom.handle(self.session, self.request, 1), [])
        self.context.assert_not_called()
        self.opening.assert_not_called()


if __name__ == '__main__':
    unittest.main()
