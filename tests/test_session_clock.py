"""Clock layout/boundary and session-handshake regression for the pinned DX11 client."""
import struct,unittest
from unittest.mock import patch
from els_server.protocol.session_clock import session_clock_ack
from els_server.protocol.local_messages import responses
from els_server.domain.local_session import LocalSession
from els_server.protocol.protocol_codec import Event


class SessionClockTests(unittest.TestCase):
    def test_wire_fields_and_millisecond_boundary(self):
        for ms in (0,999,1000,1792048000123,2147483648000):
            event=session_clock_ack(unix_ms=ms)
            self.assertEqual((event.event_id,event.kind),(0x201,0x1f0))
            self.assertEqual(len(event.payload),48)
            self.assertEqual(struct.unpack('>IQQQIQQ',event.payload),(0,ms//1000,0,0,ms%1000,0,0))
        for ms in (-1,True,1.0,2**63):
            with self.assertRaises(ValueError):session_clock_ack(unix_ms=ms)

    def test_dx11_handshake_and_refresh(self):
        session=LocalSession(client_build='dx11_260923')
        for kind in (0x1a,0x1e,0x35):session.handle(Event(0x202,kind=kind))
        with patch('els_server.protocol.session_clock.time.time_ns',return_value=1792048000123000000):
            event=session.handle(Event(0x202,kind=0x1ef))[0]
        self.assertEqual(session.phase,'session_ready')
        self.assertEqual(event.payload,session_clock_ack(unix_ms=1792048000123).payload)
        # A repeated clock exchange resets the native tick origin, so it must
        # return fresh absolute time rather than replaying a stale timestamp.
        with patch('els_server.protocol.session_clock.time.time_ns',return_value=1792048010456000000):
            again=session.handle(Event(0x202,kind=0x1ef))[0]
        self.assertEqual(again.payload,session_clock_ack(unix_ms=1792048010456).payload)
        self.assertEqual(responses(0x1ef,'legacy')[0].payload,bytes(48))


if __name__=='__main__':unittest.main()
