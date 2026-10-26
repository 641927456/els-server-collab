"""Original 9FE/9FF scalar/set grammar; no dispatch or market population."""
from dataclasses import dataclass
import struct

PAGE_SIZE = 5000
I32_MAX = 2**31 - 1


@dataclass(frozen=True)
class MetadataRequest:
    kind: int
    cursor: int


def request(payload):
    if type(payload) is not bytes or len(payload) != 5:
        raise ValueError('9FE requires exactly u8 type + i32 cursor')
    kind, cursor = struct.unpack('>Bi', payload)
    if kind not in (1, 2, 3, 4) or cursor < -1:
        raise ValueError('9FE type or cursor')
    return MetadataRequest(kind, cursor)


def acknowledgement(kind, identifiers=(), *, result=0):
    if type(kind) is not int or kind not in (1, 2, 3, 4):
        raise ValueError('9FF type')
    if type(result) is not int or not -2**31 <= result <= I32_MAX:
        raise ValueError('9FF signed result')
    values = tuple(identifiers)
    minimum = 0 if kind == 2 else 1            # Original option lists retain zero socket placeholders
    if any(type(value) is not int or not minimum <= value <= I32_MAX for value in values):
        raise ValueError('9FF namespace ID')
    values = tuple(sorted(set(values)))
    if len(values) > PAGE_SIZE or result and values:
        raise ValueError('9FF page or rejected response changes')
    return struct.pack('>iBI', result, kind, len(values)) + b''.join(
        struct.pack('>i', value) for value in values)


def rejection(kind, result):
    if type(result) is not int or result == 0:
        raise ValueError('Unavailable metadata must have an explicit error')
    return acknowledgement(kind, result=result)
