"""Compare independent encoding against real wire bytes and native plaintext."""
import hashlib
import hmac
import struct
import sys
import unittest
from pathlib import Path
from Crypto.Cipher import DES
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from protocol_codec import *


class CodecTest(unittest.TestCase):
    def setUp(self):
        self.welcome = (BASE/'analysis/protocol-fixtures/welcome-capture.bin').read_bytes()
        self.frame = decode_frame(self.welcome, BOOTSTRAP_KEYS, expected_sequence=1)
        self.event = decode_event(self.frame.plaintext)
        self.spi, self.keys = read_welcome(self.event)

    def test_welcome_matches_native_and_rebuild(self):
        native = (BASE/'analysis/runs/20261012-135943-101293/welcome-plaintext.bin').read_bytes()
        self.assertEqual(self.frame.plaintext, native)
        self.assertEqual(encode_event(welcome_event(self.keys, self.spi)), native)
        self.assertEqual(encode_frame(native, BOOTSTRAP_KEYS, spi=self.frame.spi,
                                     sequence=1, secure_sequence=self.frame.secure_sequence,
                                     iv=self.frame.iv), self.welcome)

    def test_followup_matches_native_and_rebuild(self):
        wire = (BASE/'analysis/protocol-fixtures/post-init-capture.bin').read_bytes()
        frame = decode_frame(wire, self.keys, expected_sequence=2)
        native = (BASE/'analysis/runs/20261012-140230-597200/plaintext-1791784956302.bin').read_bytes()
        self.assertEqual(frame.plaintext, native)
        self.assertEqual(encode_event(decode_event(native)), native)
        self.assertEqual(encode_frame(native, self.keys, spi=frame.spi, sequence=frame.sequence,
                                     secure_sequence=frame.secure_sequence, iv=frame.iv), wire)

    def test_real_client_response_and_fragmentation(self):
        raw = (BASE/'analysis/runs/20261012-140230-597200/local-bootstrap-connection-1.bin').read_bytes()
        reader = FrameReader(); frames = []
        for byte in raw:
            frames.extend(reader.feed(bytes([byte])))
        self.assertEqual(len(frames), 3)
        events = []
        for seq, wire in enumerate(frames, 1):
            frame = decode_frame(wire, self.keys, expected_sequence=seq)
            event = decode_event(frame.plaintext); events.append(event)
            self.assertEqual(encode_event(event), frame.plaintext)
            self.assertEqual(encode_frame(frame.plaintext, self.keys, spi=frame.spi,
                                         sequence=seq, secure_sequence=frame.secure_sequence, iv=frame.iv), wire)
        self.assertEqual((events[0].event_id, events[0].kind, events[0].performers), (1026, 3392, (0,)))
        self.assertEqual([(e.event_id, e.kind) for e in events[1:]], [(0, 0), (0, 0)])
        self.assertFalse(reader.buffer)

    def test_reject_bad_mac_sequence_length_and_padding(self):
        damaged = bytearray(self.welcome); damaged[-1] ^= 1
        with self.assertRaisesRegex(ProtocolError, 'authentication'): decode_frame(damaged, BOOTSTRAP_KEYS)
        with self.assertRaisesRegex(ProtocolError, 'sequence'): decode_frame(self.welcome, BOOTSTRAP_KEYS, expected_sequence=2)
        with self.assertRaisesRegex(ProtocolError, 'length'): decode_frame(self.welcome+b'x', BOOTSTRAP_KEYS)
        body = bytearray(self.welcome[8:])
        padded = bytearray(DES.new(BOOTSTRAP_KEYS.encryption, DES.MODE_CBC, body[6:14]).decrypt(body[14:-10]))
        padded[-2] ^= 1
        body[14:-10] = DES.new(BOOTSTRAP_KEYS.encryption, DES.MODE_CBC, body[6:14]).encrypt(padded)
        body[-10:] = hmac.new(BOOTSTRAP_KEYS.mac, body[:-10], hashlib.md5).digest()[:10]
        with self.assertRaisesRegex(ProtocolError, 'padding'):
            decode_frame(self.welcome[:8]+body, BOOTSTRAP_KEYS)


if __name__ == '__main__': unittest.main()
