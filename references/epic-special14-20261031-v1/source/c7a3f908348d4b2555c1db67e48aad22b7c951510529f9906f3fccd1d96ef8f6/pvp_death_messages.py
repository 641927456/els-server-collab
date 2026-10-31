"""Finite current two-player death notices; never establishes a death source.

Original A7/AA parsing remains protocol.known_resurrection. Current A9
BA76A0/C4E480 -> PvPTeam.C931D0 reads the three player UIDs. Ordinary
NPC=-1 branch does not consume the three modern extra fields or final Q;
they retain native constructor zero, without assigning unknown meanings.
316CF00 -> 2BE9660/C77330 and DAF020 consume 9A's two ordered maps.
316D1F0 consumes the two team-score bytes. The caller owns authorization.
"""
import struct
from els_server.protocol.protocol_codec import Event


def _uid(value):
    if type(value) is not int or not 1 <= value < 2**63:
        raise ValueError('PvP original player UID')
    return value


def killed(victim_uid, killer_uid, maximum_damage_uid):
    """Authenticated victim and its one admitted opponent, no NPC path."""
    _uid(victim_uid); _uid(killer_uid); _uid(maximum_damage_uid)
    if victim_uid == killer_uid or maximum_damage_uid != killer_uid:
        raise ValueError('PvP finite opponent death source')
    return Event(0x201, kind=0xa9, payload=struct.pack(
        '>iQQQQiiQ', -1, killer_uid, maximum_damage_uid, victim_uid, 0, 0, 0, 0))


def scores(rows, *, red, blue):
    """Two original players' kills/deaths/maximum-damage kills.

    Current 316D0DC requires both map keys before native 1AA4CD0 updates the
    actor scoreboard. The caller supplies maximum-damage attribution from
    the admitted original A7, never from an arbitrary damage estimate.
"""
    if type(rows) is not tuple or len(rows) != 2:
        raise ValueError('PvP finite score roster')
    keys = tuple(_uid(row[0]) for row in rows)
    if len(set(keys)) != 2:
        raise ValueError('PvP duplicate score actor')
    for _, kills, deaths, maximum_damage in rows:
        if any(type(n) is not int or n not in (0, 1) for n in (kills, deaths, maximum_damage)):
            raise ValueError('PvP one-kill score')
        if maximum_damage != kills:
            raise ValueError('PvP finite one-opponent attribution')
    if any(type(n) is not int or n not in (0, 1) for n in (red, blue)):
        raise ValueError('PvP one-kill team score')
    if (red, blue) != (rows[0][1], rows[1][1]):
        raise ValueError('PvP roster-team score binding')
    if rows[0][2] != blue or rows[1][2] != red or red + blue > 1:
        raise ValueError('PvP death/kill conservation')
    body = struct.pack('>I', 2) + b''.join(struct.pack('>Qii', *row[:3])
        for row in sorted(rows)) + struct.pack('>I', 2)
    body += b''.join(struct.pack('>Qi', row[0], row[3]) for row in sorted(rows))
    return (Event(0x201, kind=0x9a, payload=body),
            Event(0x201, kind=0x9b, payload=bytes((red, blue))))
