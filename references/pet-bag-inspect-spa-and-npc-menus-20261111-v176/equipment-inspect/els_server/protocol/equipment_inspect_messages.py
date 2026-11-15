"""Current DX11 equipment inspection request and public character reply."""

import struct

from els_server.domain.character_rules import transcendental_stage
from els_server.protocol.achievement_messages import status as achievement_status
from els_server.protocol.local_messages import i32, u32, wstring
from els_server.protocol.protocol_codec import Event
from els_server.protocol.social_messages import Reader, appearance_equipment

REQUEST = 0x8BE
REPLY = 0x8BF


def request(payload):
    # 7BFD00 writes the displayed nickname and the actor's server selector.
    reader = Reader(payload)
    name = reader.text(12)
    server = reader.scalar('i')
    reader.end()
    # Town peer records use 0. Character lookup may specify the same server as 1.
    if not name or server not in (0, 1):
        raise ValueError('Invalid equipment inspection target')
    return name, server


def acknowledgement(character=None, items=(), *, server=0):
    # 2309A00 -> C4DCD0: result, D9E520 connection profile, DB4880
    # optional map, two form selectors, DA4C60 inspected actor.
    c = character or {'uid': 0, 'name': '', 'unit_class': 0, 'level': 0}
    uid = c['uid']
    name = wstring(c['name'])
    unit_class = c['unit_class']
    level = c['level']
    stage = transcendental_stage(c)
    active = c.get('luciel_active_unit', 0)
    style = c.get('luciel_style', 0)

    # The connection profile has the native identity, level and server.
    # Public account/PvP/guild extras without a source take their empty values.
    profile = (
        struct.pack('>QIHiB', uid, 0, unit_class, stage, level) + name
        + bytes(1) + bytes(6 * 4)  # rank, points, ranking, wins, losses, kills, channel
        + bytes(1 + 4 + 8 + 8 + 2 + 4 + 1)  # state, room/party and admission flags
        + wstring('') + bytes(1) + i32(0) + i32(server)
        + struct.pack('>iiiQI', 0, 0, 0, 0, 0) + bytes(1)
    )

    # DA4C60's two public item vectors use D9A9D0, as in town peer updates.
    # The active form uses the character's persisted worn gear.
    actor = (
        struct.pack('>Q', uid) + name + struct.pack('>HiBBBB', unit_class, stage, active, style, level, 0)
        + appearance_equipment(items) + u32(0)
        + u32(0) + i32(c.get('title', 0))
        + bytes(25) + u32(0) + i32(0)  # DB0D10, DB2880, optional integer
        + achievement_status((0, 0, 0, 0), (), False) + u32(0)
    )
    payload = i32(0 if character is not None else 1) + profile + u32(0) + i32(active) + i32(style) + actor
    return Event(0x201, kind=REPLY, payload=payload)
