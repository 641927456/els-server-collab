"""Finite complete D9A550 item grammar used by actual offer records.

The unsupported dynamic map at DTO+33D is refused explicitly. All bytes are
consumed, including explicit pet/mount fields; missing fields never mean zero.
"""
from dataclasses import dataclass
import struct


@dataclass(frozen=True)
class NativeItemMetadata:
    template: int
    count: int
    option_groups: tuple
    pet_data_id: int
    mount_data_id: int


class _Reader:
    def __init__(self, raw):
        if type(raw) is not bytes or not 1 <= len(raw) <= 262144:
            raise ValueError('Complete native offer item bytes required')
        self.raw, self.pos = raw, 0

    def take(self, size):
        if size < 0 or self.pos + size > len(self.raw):
            raise ValueError('Truncated native offer item')
        value = self.raw[self.pos:self.pos + size]
        self.pos += size
        return value

    def integer(self, kind='i'):
        return struct.unpack('>' + kind, self.take(struct.calcsize('>' + kind)))[0]

    def count(self, maximum):
        count = self.integer('I')
        if count > maximum:
            raise ValueError('Native offer item vector bound')
        return count

    def boolean(self):
        if self.integer('B') not in (0, 1):
            raise ValueError('Native offer item boolean')


def read_item(raw):
    r = _Reader(raw)
    template = r.integer()                    # DTO+0
    r.take(1)                                 # +4 metadata
    count = r.integer()                       # +5 count
    if not 0 < template < 2**31 or not 0 < count < 2**31:
        raise ValueError('Native offer item template/count')
    r.take(2 + 1 + 1)                          # +9/+B/+C
    r.take(4 * r.count(4))                     # +D attributes
    if r.count(33) != 33:                      # +25 exact fixed array
        raise ValueError('Native offer item requires all 33 option groups')
    groups = tuple(tuple(r.integer() for _ in range(r.count(64))) for _ in range(33))
    if any(value < 0 for group in groups for value in group):
        raise ValueError('Native offer option ID')
    if r.integer('I') != 0:                    # +33D unknown map is never guessed
        raise ValueError('Unsupported native offer DTO+33D dynamic map')
    r.take(1 + 2)                              # +34D/+34E
    text = r.take(r.count(2048))               # +350 UTF16 byte length
    if len(text) % 2:
        raise ValueError('Native offer UTF16 byte length')
    text.decode('utf-16le')
    r.take(8 + 4)                              # +370 lock/+378 appearance
    r.boolean()                               # +37C
    for _ in range(2):                        # +37D/+389 native fixed triples
        if r.count(3) != 3:
            raise ValueError('Native offer fixed color triple')
        r.take(12)
    r.boolean()                               # +395
    r.take(1 + 4 * 4 + 1 + 4 * 2 + 4)         # +396..+3B3
    pet_fields = tuple(r.integer() for _ in range(7))       # +3B4..+3CC
    mount_fields = tuple(r.integer() for _ in range(7))     # +3D0..+3E8
    r.take(8)                                 # +3EC two scalar cartridge fields
    if r.pos != len(raw):
        raise ValueError('Trailing native offer item bytes')
    return NativeItemMetadata(template, count, groups, pet_fields[0], mount_fields[0])
