"""Exercise the original menu's wire envelope without private game assets."""
import dataclasses
import os
import sqlite3
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from els_server.domain import character_custom
from els_server.protocol.protocol_codec import (
    BOOTSTRAP_KEYS, Event, decode_event, decode_frame, encode_event, encode_frame,
)


class CharacterCustomOpeningTests(unittest.TestCase):
    def setUp(self):
        # panel_admitted() re-checks the DX11 build, town/dungeon phase and the
        # current instance lease, so the fixture has to carry the same fields
        # a live game session does.
        self.session = types.SimpleNamespace(
            client_build='dx11_260923', item_test=True, role='game', phase='town_ready',
            account=types.SimpleNamespace(uid=1001, account_id=17,
                characters=object(), store=types.SimpleNamespace(path='unused.sqlite3')))
        self.lease = self.enterContext(patch(
            'els_server.domain.dungeon_equipment_loot_flow.current_lease', return_value=True))
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
        # No current instance lease: the opener must stay silent.
        self.admitted.return_value = False
        self.lease.return_value = False
        self.assertEqual(character_custom.handle(self.session, self.request, 1), [])
        self.context.assert_not_called()
        self.opening.assert_not_called()

    def test_village_opener_replays_the_saved_selection(self):
        # The rows paint themselves from the 4CD/4CC/18E trio, not from the 635
        # opener: a window opened in town therefore showed the career default
        # for a slot the save had already set, while the game itself kept
        # applying it through the login 18E. Only the chosen rows are
        # registered - replaying one 4CD per owned row is thousands of events on
        # a fully unlocked save, and the client drops a burst that size whole.
        stored = {19: character_custom.canonical(15211)}
        owned = {19: [character_custom.canonical(15211)],
                 16: [character_custom.canonical(8000)],
                 3: [character_custom.canonical(13011)]}
        self.session.account.character = lambda: {'title': 0}
        self.enterContext(patch.dict(sys.modules, {'els_server.storage.character_custom':
            types.SimpleNamespace(opening_info=self.opening,
                                  snapshot=lambda db, uid: {'owned': owned, 'selected': stored})}))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'session.sqlite3')
            sqlite3.connect(path).close()
            self.session.account.store = types.SimpleNamespace(path=path)
            events = character_custom.handle(self.session, self.request, 3)
        self.assertEqual([event.kind for event in events], [0x635, 0x4cd, 0x4cc, 0x18e])
        # The registration names the book that grants the row. A zero there
        # leaves the selected row unresolved and the window paints the base
        # custom (basic frame / basic wake-up) instead of the chosen one.
        self.assertEqual(struct.unpack('>i', events[1].payload[:4])[0], 472284)
        self.assertEqual(struct.unpack('>i', events[1].payload[:4])[0],
                         character_custom.template_of(15211))

    def test_unreadable_store_still_opens_the_window(self):
        # The replay is optional; a session whose store cannot be read must not
        # lose the panel over it.
        self.session.account.store = types.SimpleNamespace(path=os.path.join(
            tempfile.gettempdir(), 'character-custom-missing', 'absent.sqlite3'))
        self.assertEqual(character_custom.handle(self.session, self.request, 4), [self.response])


if __name__ == '__main__':
    unittest.main()
