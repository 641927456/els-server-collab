"""Current C4E700/0x106 notification body, with no client-side changes.

This is the wire encoder, not a final-stat calculator. Every state field must
be supplied explicitly by a qualified server snapshot. In particular, neither
empty containers nor zero power mean "keep the existing client value".
No running dispatcher imports this candidate until the producer is qualified.
"""
from dataclasses import dataclass
import math
import struct


OPCODE = 0x106
MAX_PAYLOAD = 65500
MAX_ENTRIES = 512


@dataclass(frozen=True)
class NamedOption:
    first: int
    second: int
    first_text: str
    second_text: str
    third: int


@dataclass(frozen=True)
class SourceGroup:
    # DD25B0 stores these as set<int>, vector<int>, bool, uint64, uint64.
    # Names intentionally do not guess whether the two uint64s are timestamps.
    identities: tuple
    ordered_values: tuple
    enabled: bool
    first_token: int
    second_token: int


@dataclass(frozen=True)
class ProgressRecord:
    # DB29A0: int32, int32, uint64, uint8; not the existing ERP wire layout.
    first: int
    second: int
    token: int
    flag: int


@dataclass(frozen=True)
class AttributeNotification:
    reason: int
    owner_uid: int
    # ((bag, slot, current_item_or_None), ...); reuse current 105 item reader.
    equipment_changes: tuple
    first_seven: tuple
    second_seven: tuple
    title_id: int
    named_options: tuple
    source_groups_enabled: bool
    source_groups: tuple
    numeric_options: tuple
    progress: ProgressRecord
    power: float


def _integer(value, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError('Native attribute integer range')
    return value


def _i32(value):
    return struct.pack('>i', _integer(value, -(1 << 31), (1 << 31)-1))


def _u64(value):
    return struct.pack('>Q', _integer(value, 0, (1 << 64)-1))


def _boolean(value):
    if type(value) is not bool:
        raise ValueError('Explicit native attribute bool required')
    return bytes((value,))


def _rows(value):
    if type(value) is not tuple or len(value) > MAX_ENTRIES:
        raise ValueError('Bounded immutable native attribute rows required')
    return struct.pack('>I', len(value))


def _float(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Finite native attribute float required')
    try:
        raw = struct.pack('>f', value)
    except (OverflowError, struct.error) as error:
        raise ValueError('Native attribute float32 range') from error
    if not math.isfinite(struct.unpack('>f', raw)[0]):
        raise ValueError('Native attribute float32 overflow')
    return raw


def _seven(values):
    if type(values) is not tuple or len(values) != 7:
        raise ValueError('Two explicit native seven-float groups required')
    return b''.join(_float(value) for value in values)


def _text(value):
    if type(value) is not str:
        raise ValueError('Native option text required')
    # 3B6D640 prefixes byte length; 164530 copies wchar_t bytes unchanged.
    raw = value.encode('utf-16le')
    if len(raw) > 8192:
        raise ValueError('Native option text bound')
    return struct.pack('>I', len(raw)) + raw


def _map(rows, value_encoder):
    prefix = _rows(rows)
    previous = -129
    out = []
    for key, value in rows:
        _integer(key, -128, 127)
        if key <= previous:
            raise ValueError('Native signed-char map must be unique and ordered')
        previous = key
        out.append(struct.pack('>b', key) + value_encoder(value))
    return prefix + b''.join(out)


def _named(values):
    out = [_rows(values)]
    for row in values:
        if type(row) is not NamedOption:
            raise ValueError('Explicit native named option required')
        out.append(_i32(row.first) + _i32(row.second) + _text(row.first_text)
                   + _text(row.second_text) + _i32(row.third))
    return b''.join(out)


def _pairs(values):
    return _rows(values) + b''.join(_i32(first)+_i32(second) for first, second in values)


def _groups(values):
    out = [_rows(values)]
    for row in values:
        if type(row) is not SourceGroup:
            raise ValueError('Explicit native source group required')
        _rows(row.identities)
        if tuple(sorted(set(row.identities))) != row.identities:
            raise ValueError('Native source identity set must be unique and ordered')
        out.append(_rows(row.identities) + b''.join(_i32(v) for v in row.identities)
                   + _rows(row.ordered_values) + b''.join(_i32(v) for v in row.ordered_values)
                   + _boolean(row.enabled) + _u64(row.first_token) + _u64(row.second_token))
    return b''.join(out)


def _equipment(changes):
    out = [_rows(changes)]
    if not changes:
        return out[0]
    from els_server.domain.fashion_state import empty_record, record
    seen = set()
    for group, slot, item in changes:
        _integer(group, 0, 127)
        _integer(slot, -32768, 32767)
        if (group, slot) in seen:
            raise ValueError('Duplicate native equipment change position')
        seen.add((group, slot))
        if item is None:
            out.append(empty_record(group, slot))
        else:
            if (item['group'], item['slot']) != (group, slot):
                raise ValueError('Native equipment change position mismatch')
            out.append(record(item))
    return b''.join(out)


def encode(notification):
    """Encode an explicitly supplied snapshot; never calculate or trust C2S stats."""
    if type(notification) is not AttributeNotification:
        raise ValueError('Explicit native attribute notification required')
    n = notification
    _integer(n.reason, -128, 127)
    _integer(n.owner_uid, 1, (1 << 64)-1)
    p = n.progress
    if type(p) is not ProgressRecord:
        raise ValueError('Explicit native progress record required')
    body = (struct.pack('>b', n.reason) + _u64(n.owner_uid)
            + _equipment(n.equipment_changes) + _seven(n.first_seven) + _seven(n.second_seven)
            + _i32(n.title_id) + _map(n.named_options, _named) + _boolean(n.source_groups_enabled)
            + _groups(n.source_groups) + _map(n.numeric_options, _pairs)
            + _i32(p.first) + _i32(p.second) + _u64(p.token)
            + bytes((_integer(p.flag, 0, 255),)) + _float(n.power))
    if len(body) > MAX_PAYLOAD:
        raise ValueError('Native attribute notification size bound')
    return body
