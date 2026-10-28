"""Current-client guild request prefixes and saved membership projection.

Source: 6c6b5180 client, runtime c8815e00. This leaf does not admit a
producer or invent the remaining GuildInfo state. Storage/dispatch wiring
is intentionally absent until that complete source contract is closed.
"""
import struct


def _string(payload, offset):
    if offset + 4 > len(payload):
        raise ValueError('Truncated guild string count')
    size = struct.unpack_from('>I', payload, offset)[0]
    offset += 4
    if size % 2 or size > 8192 or offset + size > len(payload):
        raise ValueError('Guild string byte count')
    value = payload[offset:offset + size].decode('utf-16le', errors='strict')
    if '\0' in value:
        raise ValueError('Guild string embedded terminator')
    return value, offset + size


def _payload(payload, minimum):
    if type(payload) is not bytes or not minimum <= len(payload) <= 16400:
        raise ValueError('Guild request payload size/type')


def create_request(payload):
    # 326E8C0: 276 = item UID Q, guild name wstring, message wstring.
    _payload(payload, 16)
    item_uid = struct.unpack_from('>Q', payload)[0]
    name, offset = _string(payload, 8)
    message, offset = _string(payload, offset)
    if not item_uid or offset != len(payload):
        raise ValueError('Guild create instance/trailing bytes')
    return item_uid, name, message


def invite_request(payload):
    # 3270450: 285 = recipient nickname followed by recipient UID Q.
    # UI has both nickname and UID routes; storage must resolve and compare
    # whichever selectors are supplied, against the actual online character.
    _payload(payload, 12)
    name, offset = _string(payload, 0)
    if offset + 8 != len(payload):
        raise ValueError('Guild invite trailing bytes')
    uid = struct.unpack_from('>Q', payload, offset)[0]
    if not name and not uid:
        raise ValueError('Guild invite lacks recipient')
    return name, uid


def join_reply_request(payload):
    # 32707D0: 288 = guild ID i32, inviter nickname, response i32.
    # Native confirm 3246960 sends zero; nonzero responses must never join.
    _payload(payload, 12)
    guild_id = struct.unpack_from('>i', payload)[0]
    inviter, offset = _string(payload, 4)
    if guild_id <= 0 or not inviter or offset + 4 != len(payload):
        raise ValueError('Guild reply identity/trailing bytes')
    return guild_id, inviter, struct.unpack_from('>i', payload, offset)[0]


def saved_membership_wire(guild_id, name, grade, original_empty_group):
    # D9B170 -> DB0BA0; 87A6E0 copies DTO 30B/30F/32F to Unit
    # 26D0/26D8/26F8. The original empty group is exactly 66 wire bytes:
    # i32, wstring, byte, {i32,i32,Q}, byte, byte, i32, wstring, bool,
    # map, vector, i32, {f32,f32,f32}, byte, byte, i32.
    # Preserve its remaining 57 bytes. No guild feature state is fabricated.
    if type(original_empty_group) is not bytes or original_empty_group != bytes(66):
        raise ValueError('Unbound empty guild group')
    if type(guild_id) is not int or not 0 < guild_id <= 2**31 - 1:
        raise ValueError('Guild identity bound')
    if type(grade) is not int or grade not in (1, 2, 3, 4, 5, 6):
        raise ValueError('Guild member grade')
    if type(name) is not str or not name or '\0' in name:
        raise ValueError('Guild name type/terminator')
    raw = name.encode('utf-16le', errors='strict')
    if len(raw) > 8192:
        raise ValueError('Guild name wire bound')
    from els_server.domain.guild_bank_rules import permissions_wire
    return (struct.pack('>iI', guild_id, len(raw)) + raw + bytes((grade,))
            + original_empty_group[9:36] + permissions_wire() + original_empty_group[40:])
