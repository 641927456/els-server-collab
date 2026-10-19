"""Verified x2 bootstrap framing and secure event codec for this client build.

Evidence: analysis/protocol-functions and captured native plaintext. This module
does not implement account authentication or game state.
"""
from dataclasses import dataclass
import hashlib
import hmac
import secrets
import struct
from Crypto.Cipher import DES


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Keys:
    mac: bytes
    encryption: bytes

    def __post_init__(self):
        if len(self.mac) != 8 or len(self.encryption) != 8:
            raise ProtocolError('This build requires two 8-byte keys')


# Little-endian immediates at RVA 0x3a0cc90 (default SASInfo constructor).
BOOTSTRAP_KEYS = Keys(bytes.fromhex('c0d3bdc3b7ceb8b8'), bytes.fromhex('c7d8c4bfb5e9c0fd'))


@dataclass(frozen=True)
class SecureFrame:
    sequence: int
    spi: int
    secure_sequence: int
    iv: bytes
    plaintext: bytes


@dataclass(frozen=True)
class Event:
    event_id: int
    performers: tuple[int, ...] = ()
    uid: int = 0xffffffffffffffff
    target_uid: int = 0xffffffffffffffff
    kind: int = 0
    payload: bytes = b''
    payload_mode: int = 0


def unpad(data):
    if not data:
        raise ProtocolError('Empty padded payload')
    n = data[-1]
    if n + 1 > len(data) or data[-n-1:-1] != bytes(range(1, n+1)):
        raise ProtocolError('Invalid ascending padding')
    return data[:-n-1]


def encode_frame(plaintext, keys, *, spi=0, sequence=1, secure_sequence=None, iv=None):
    iv = secrets.token_bytes(8) if iv is None else iv
    if len(iv) != 8:
        raise ProtocolError('IV must contain 8 bytes')
    n = (7-len(plaintext)) % 8
    padded = plaintext + bytes(range(1, n+1)) + bytes([n])
    body = struct.pack('<HI', spi, sequence if secure_sequence is None else secure_sequence) + iv
    body += DES.new(keys.encryption, DES.MODE_CBC, iv).encrypt(padded)
    body += hmac.new(keys.mac, body, hashlib.md5).digest()[:10]
    return struct.pack('<II', len(body)+8, sequence) + body


def decode_frame(wire, keys, *, expected_sequence=None):
    if len(wire) < 40:
        raise ProtocolError('Truncated secure frame')
    length, sequence = struct.unpack_from('<II', wire)
    if length != len(wire) or length > 1024*1024:
        raise ProtocolError('Invalid frame length')
    if expected_sequence is not None and sequence != expected_sequence:
        raise ProtocolError('Unexpected outer sequence')
    body = wire[8:]
    if not hmac.compare_digest(hmac.new(keys.mac, body[:-10], hashlib.md5).digest()[:10], body[-10:]):
        raise ProtocolError('Invalid authentication tag')
    spi, secure_sequence = struct.unpack_from('<HI', body)
    iv, ciphertext = body[6:14], body[14:-10]
    if not ciphertext or len(ciphertext) % 8:
        raise ProtocolError('Invalid DES ciphertext length')
    return SecureFrame(sequence, spi, secure_sequence, iv,
                       unpad(DES.new(keys.encryption, DES.MODE_CBC, iv).decrypt(ciphertext)))


class FrameReader:
    """Accumulate TCP chunks; WSABUF boundaries are not frame boundaries."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk):
        self.buffer.extend(chunk)
        result = []
        while len(self.buffer) >= 8:
            length = struct.unpack_from('<I', self.buffer)[0]
            if not 40 <= length <= 1024*1024:
                raise ProtocolError('Invalid buffered frame length')
            if len(self.buffer) < length:
                break
            result.append(bytes(self.buffer[:length]))
            del self.buffer[:length]
        return result


def encode_event(event):
    data = struct.pack('>II', event.event_id, len(event.performers))
    data += b''.join(struct.pack('>Q', p) for p in event.performers)
    data += struct.pack('>QQHI', event.uid, event.target_uid, event.kind, len(event.payload))
    return data + (bytes([event.payload_mode]) + event.payload if event.payload else b'')


def decode_event(data):
    if len(data) < 30:
        raise ProtocolError('Truncated event')
    event_id, count = struct.unpack_from('>II', data)
    offset = 8 + count*8
    if offset+22 > len(data):
        raise ProtocolError('Truncated performer list')
    performers = tuple(struct.unpack_from('>Q', data, 8+i*8)[0] for i in range(count))
    uid, target_uid, kind, size = struct.unpack_from('>QQHI', data, offset)
    offset += 22
    if len(data) != offset + size + (1 if size else 0):
        raise ProtocolError('Invalid event payload size')
    mode = data[offset] if size else 0
    return Event(event_id, performers, uid, target_uid, kind,
                 data[offset+1:] if size else b'', mode)


def welcome_event(keys, spi):
    # uint16 SPI, two length-prefixed keys, three uint32 algorithm selectors.
    payload = struct.pack('>HI', spi, 8) + keys.mac
    payload += struct.pack('>I', 8) + keys.encryption + struct.pack('>III', 1, 0, 0)
    return Event(0, kind=1, payload=payload)


def read_welcome(event):
    if event.event_id != 0 or event.kind != 1 or event.payload_mode != 0 or len(event.payload) != 38:
        raise ProtocolError('Unsupported welcome event')
    p = event.payload
    if struct.unpack_from('>I', p, 2)[0] != 8 or struct.unpack_from('>I', p, 14)[0] != 8 or p[26:] != struct.pack('>III', 1, 0, 0):
        raise ProtocolError('Unsupported welcome algorithms or key sizes')
    return struct.unpack_from('>H', p)[0], Keys(p[6:14], p[18:26])
