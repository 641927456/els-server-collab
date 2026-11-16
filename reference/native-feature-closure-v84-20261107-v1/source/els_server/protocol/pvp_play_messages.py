"""Finite official-1v1 wire leaves from the pinned current native consumers.

No matchmaking, clock, battle simulation or award authority is implemented here.
349: 2D66FE0; 9C/9D/9F: 3165F10; 9E: 1AB7AC0/C68F80/DA2F50.
9E is the nested play-report body itself, unlike the existing 67 envelope.
"""
from dataclasses import dataclass
import math
import struct

from els_server.protocol.protocol_codec import Event


@dataclass(frozen=True)
class HPReport:
    hp: float
    active_side: int
    raw: bytes
    maximum_hp: float | None = None
    statistics: dict | None = None


def hp_report(payload, *, statistics=False):
    """Parse all DA2F50 fields without interpreting telemetry as awards.

    Absolute HP comes from 1AB6EB0/1AB6F3E, not a win/percentage claim.
    The caller must bind this report to its own authenticated, loaded actor
    and a live server-issued report request. This codec grants no eligibility.
    """
    # Dungeon reports include four per-skill maps and grow with a full run.
    # Use the existing transport frame bound; keep the PvP contract unchanged.
    maximum_size=1024*1024 if statistics else 8192
    if type(payload) is not bytes or not 182 <= len(payload) <= maximum_size:
        raise ValueError('PvP play-report size')
    original=payload;maximum=None
    offset = 0

    def take(size):
        nonlocal offset
        if size > len(payload) - offset:
            raise ValueError('PvP play-report bound')
        result = payload[offset:offset + size]
        offset += size
        return result

    def unpack(fmt):
        return struct.unpack('>' + fmt, take(struct.calcsize('>' + fmt)))

    def floats(count):
        values = unpack('f' * count)
        if not all(math.isfinite(value) for value in values):
            raise ValueError('PvP nonfinite native report')
        return values

    def ordered(keyfmt, value_size, nested=False, numeric=False):
        count, = unpack('I')
        keysize = struct.calcsize('>' + keyfmt)
        if count > (len(payload) - offset) // (keysize + (4 if nested else value_size)):
            raise ValueError('PvP play-report count')
        previous = None
        rows = {}
        for _ in range(count):
            key, = unpack(keyfmt)
            if previous is not None and key <= previous:
                raise ValueError('PvP play-report order')
            previous = key
            if nested:
                rows[key] = ordered('i', 4, numeric=numeric)
            elif numeric:
                value, = floats(1)
                if value < 0:raise ValueError('Negative native statistic')
                rows[key] = value
            else:
                take(value_size)
        return rows

    hp, = floats(1)
    if hp < 0:
        raise ValueError('PvP negative current HP')
    take(4)
    ordered('i', 4)
    take(12)
    floats(1)
    received, = unpack('i')
    damage = tuple(ordered('Q', 4, numeric=statistics) for _ in range(8))
    recovery = floats(4)
    cooldown = ordered('Q', 4, numeric=statistics)
    floats(1)
    take(28)
    take(1)
    floats(4)
    active, = unpack('B')
    if active not in (0, 1):
        raise ValueError('PvP active actor side')
    take(28)
    skills = tuple(ordered('Q', 0, nested=True, numeric=statistics) for _ in range(4))
    ordered('i', 0)
    local_cooldown=None
    # Extensions begin after the complete original DTO, never by searching
    # arbitrary UID/value bytes at the end of an otherwise valid report.
    if payload[offset:offset+4]==b'PVP1':
        take(4);maximum,=floats(1)
        if maximum<=0:raise ValueError('PvP native maximum HP')
    elif statistics and payload[offset:offset+4]==b'PVE1':
        take(4);local_cooldown=ordered('Q',4,numeric=True)
    if offset != len(payload):
        raise ValueError('PvP play-report trailing bytes')
    if maximum is not None and hp>maximum:raise ValueError('PvP native HP exceeds current maximum')
    values = None
    if statistics:
        if received < 0 or any(v < 0 for v in recovery):raise ValueError('Negative native statistic')
        values = dict(damage=damage, received=received, recovery=recovery,
                      cooldown=cooldown, local_cooldown=local_cooldown, skills=skills)
    return HPReport(hp, active, original, maximum, values)


def matched(match_uid):
    """349 ordinary match; retain constructor defaults of unused additions.

    Current handler consumes UID+0 for the ordinary callback. The second UID
    and byte retain its zero constructor values; final -1 is its ordinary
    selection sentinel (the separate challenge branch uses a concrete value).
    """
    if type(match_uid) is not int or not 1 <= match_uid < 2**63:
        raise ValueError('PvP server match identity')
    return Event(0x201, kind=0x349,
                 payload=struct.pack('>QQBi', match_uid, 0, 0, -1))


def remaining_time(seconds):
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 <= seconds <= 300:
        raise ValueError('PvP authorized remaining time')
    return Event(0x201, kind=0x9c, payload=struct.pack('>f', seconds))


def time_over():
    return Event(0x201, kind=0x9d, payload=b'')


def report_ack(result):
    if type(result) is not int or not -(2**31) <= result < 2**31:
        raise ValueError('PvP report result')
    return Event(0x201, kind=0x9f, payload=struct.pack('>i', result))
