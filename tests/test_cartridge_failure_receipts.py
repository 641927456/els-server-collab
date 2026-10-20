"""Unadmitted Cartridge operations must terminate waits without reading state."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from els_server.domain.equipment_cartridge_flow import handle
from els_server.protocol.protocol_codec import Event


class NoStateSession:
    client_build = 'dx11_260923'
    role = 'game'

    @property
    def account(self):
        raise AssertionError('Rejection must not read or mutate account state')


class CartridgeFailureTests(unittest.TestCase):
    def test_unadmitted_requests_never_report_success(self):
        session = NoStateSession()
        for item_test in (False, True):
            session.item_test = item_test
            for kind, size in ((0xd4e, 24), (0xd50, 16), (0xd52, 16), (0xd54, 32)):
                for payload in (b'', bytes(12), b'\xff' * 20):
                    with self.subTest(kind=kind, item_test=item_test, size=len(payload)):
                        replies = handle(session, Event(0x202, kind=kind, payload=payload))
                        self.assertEqual(len(replies), 1)
                        reply = replies[0]
                        self.assertEqual((reply.event_id, reply.kind), (0x201, kind + 1))
                        self.assertEqual(len(reply.payload), size)
                        self.assertNotEqual(struct.unpack_from('>i', reply.payload)[0], 0)

    def test_other_versions_roles_events_and_operations_are_unclaimed(self):
        session = NoStateSession()
        for event in (Event(0x201, kind=0xd4e), Event(0x202, kind=0xd4d), Event(0x202, kind=0x8d1)):
            self.assertIsNone(handle(session, event))
        session.client_build = 'unknown'
        self.assertIsNone(handle(session, Event(0x202, kind=0xd54)))
        session.client_build = 'dx11_260923'
        session.role = 'login'
        self.assertIsNone(handle(session, Event(0x202, kind=0xd54)))


if __name__ == '__main__':
    unittest.main()
