"""Current native official-match wire shapes; no admission or result producer.

Pinned c8815 image: 2E0E160/2BDE630/2BDE710 (342), 2D66B10
(343), 2D58F25/2BDE7E0 (344), 2E0E4F0 (345), 2D67450
(346), 2E0E850/2BDE8F0 (34A). Business authority stays with caller.
"""
import struct
from els_server.protocol.protocol_codec import Event


class _Reader:
    def __init__(self, payload):
        if type(payload) is not bytes:
            raise ValueError('PvP request bytes')
        self.payload = payload
        self.offset = 0

    def read(self, fmt):
        size = struct.calcsize('>' + fmt)
        if self.offset + size > len(self.payload):
            raise ValueError('Truncated PvP request')
        result = struct.unpack_from('>' + fmt, self.payload, self.offset)
        self.offset += size
        return result[0] if len(result) == 1 else result

    def boolean(self):
        value = self.read('B')
        if value not in (0, 1):
            raise ValueError('PvP Boolean')
        return bool(value)

    def count(self, width):
        count = self.read('I')
        if count > (len(self.payload) - self.offset) // width:
            raise ValueError('PvP vector count')
        return count

    def end(self):
        if self.offset != len(self.payload):
            raise ValueError('Trailing PvP request')


def registration(payload):
    """342: mode triples, opaque native i32 hint, vector<pair<UID,byte>>.

    The hint is not an authoritative rank. UI 2CC6900 emits the mode triples
    (0,1,false), (1,2,false), (1,3,false); the normal 2D666E0 path emits an
    empty final vector. Other forms require separate business qualification.
    """
    r = _Reader(payload)
    modes = tuple((r.read('B'), r.read('B'), r.boolean())
                  for _ in range(r.count(3)))
    hint = r.read('i')
    related = tuple(r.read('QB') for _ in range(r.count(9)))
    r.end()
    return modes, hint, related


def cancellation(payload):
    """345 Q: normal self-cancel UI 2CC1E80 supplies zero, not actor UID."""
    r = _Reader(payload)
    uid = r.read('Q')
    r.end()
    return uid


def confirmation(payload):
    """34A: three bools, set<i16>, final bool; no client supplied match UID."""
    r = _Reader(payload)
    flags = tuple(r.boolean() for _ in range(3))
    maps = tuple(r.read('h') for _ in range(r.count(2)))
    if tuple(sorted(set(maps))) != maps:
        raise ValueError('Noncanonical native PvP map set')
    tail = r.boolean()
    r.end()
    return flags, maps, tail


def _integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError('PvP integer')
    return value


def _boolean(value):
    if type(value) is not bool:
        raise ValueError('PvP Boolean')
    return bytes((int(value),))


def _i32(value):
    return struct.pack('>i', _integer(value, -(1 << 31), (1 << 31) - 1))


def registration_ack(result, native_flag, text):
    if type(text) is not str or '\0' in text:
        raise ValueError('PvP native text')
    raw = text.encode('utf-16le', errors='strict')
    payload = _i32(result) + _boolean(native_flag) + struct.pack('>I', len(raw)) + raw
    return Event(0x201, kind=0x343, payload=payload)


def wait_notification(estimated_seconds, modes):
    """344: caller must supply an actual queue estimate and admitted modes."""
    rows = []
    for first, second, flag in modes:
        rows.append(bytes((_integer(first, 0, 255), _integer(second, 0, 255))) + _boolean(flag))
    return Event(0x201, kind=0x344,
                 payload=_i32(estimated_seconds) + struct.pack('>I', len(rows)) + b''.join(rows))


def cancellation_ack(result, native_flag, native_uid):
    return Event(0x201, kind=0x346,
                 payload=_i32(result) + _boolean(native_flag) +
                 struct.pack('>Q', _integer(native_uid, 0, (1 << 64) - 1)))
