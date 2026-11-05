"""Profession wire layouts recovered from the pinned DX11 client.

No session handler is enabled yet. Initial level/XP rules, counter meanings and
selection failure codes must be recovered before this becomes a business API.
See analysis/integration-20261015/profession-state-findings.txt.
"""
from dataclasses import dataclass, field
import math
import struct


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Profession integer range/type')
    return value


def _map(values, *, floats=False):
    # Local encoding bound, not a recovered retail limit.
    if not isinstance(values, dict) or len(values) > 512:
        raise ValueError('Profession map bound/type')
    encoded = []
    for key, value in values.items():
        _integer(key, -(2**31), 2**31-1)
        if floats:
            if type(value) not in (int, float):
                raise ValueError('Profession float value')
            try:
                if not math.isfinite(value):
                    raise ValueError('Profession float value')
                raw = struct.pack('>f', value)
            except (OverflowError, struct.error) as exc:
                raise ValueError('Profession float range') from exc
        else:
            raw = struct.pack('>i', _integer(value, -(2**31), 2**31-1))
        encoded.append((key, struct.pack('>i', key) + raw))
    return struct.pack('>I', len(encoded)) + b''.join(raw for _, raw in sorted(encoded))


@dataclass(frozen=True)
class ProfessionState:
    profession: int = 0
    level: int = 0
    experience: int = 0
    counters: dict = field(default_factory=dict)
    progress: int = 0
    required: int = 0


def state_wire(state):
    """DB0DC0: byte, byte, int32, map<int32,int32>, int32, int32."""
    if not isinstance(state, ProfessionState):
        raise ValueError('Profession state type')
    return (struct.pack('>BBi', _integer(state.profession, 0, 3),
                        _integer(state.level, 0, 255),
                        _integer(state.experience, 0, 2**31-1))
            + _map(state.counters)
            + struct.pack('>ii', _integer(state.progress, 0, 2**31-1),
                          _integer(state.required, 0, 2**31-1)))


def select_request(payload):
    """30AD6E0 sends event202/kind4C2 with one chosen type byte."""
    if type(payload) is not bytes or len(payload) != 1 or payload[0] not in (1, 2, 3):
        raise ValueError('Profession selection request')
    return payload[0]


def counter_update(values):
    """4C5: replace supplied counter values, retaining unspecified keys.

    Native 2DF68D0 reads C62740 and passes the map to 2DF8BB0. This is a
    delta, unlike a complete snapshot; an empty map does not clear counters.
    Counter identifiers and their business meanings remain unrecovered.
    """
    return _map(values)


def level_update(uid, state, effects):
    """4C4/2DF6DF0: UID, state, map<int32,float32>; triggers level-up UI.

    The current-user branch updates state only for a matching UID. Empty
    effects retain the old effects map. State counters still use insert-only
    copy; use 4C5 for changed counter values. This is not a generic refresh.
    """
    return (struct.pack('>Q', _integer(uid, 1, 2**63-1))
            + state_wire(state) + _map(effects, floats=True))


def selection_ack(result, state, effects, *, tail_u64, tail_i32, tail_flag_a, tail_flag_b):
    """2E0B970's 4C3 parser; unknown tail values are deliberately explicit.

    DB4110 is map<int32,float32>, unlike the state's integer map. The native
    success handler stores it separately through 2DF8F00/2E1BD80. An empty
    state/counter/effect payload is 40 bytes; the in-memory DTO uses 64 bytes.
    """
    if type(tail_flag_a) is not bool or type(tail_flag_b) is not bool:
        raise ValueError('Profession tail bool')
    return (struct.pack('>i', _integer(result, -(2**31), 2**31-1))
            + state_wire(state) + _map(effects, floats=True)
            + struct.pack('>QiBB', _integer(tail_u64, 0, 2**64-1),
                          _integer(tail_i32, -(2**31), 2**31-1),
                          tail_flag_a, tail_flag_b))
