"""Original c8815e00 mentor relation packets (DB5150/DB5210/21AC650)."""
import struct
from els_server.protocol.local_messages import i32, wstring
from els_server.protocol.protocol_codec import Event

REQUESTS = frozenset((0x1e4, 0x1e8, 0x1eb, 0x714, 0x71b, 0x71f))
EMPTY_ANSWER_INFO = bytes(25)


def request(kind, payload):
    if type(payload) is not bytes:
        raise ValueError('Mentor request bytes required')
    if kind in (0x1e4, 0x1e8):
        if len(payload) != 8:
            raise ValueError('Mentor target body')
        return dict(target=struct.unpack('>Q', payload)[0])
    if kind == 0x1eb:
        # 21AE1E0 always sends DF6040's default DTO. It never echoes 1EA.
        if len(payload) != 38 or payload[8:33] != EMPTY_ANSWER_INFO or payload[33] not in (0, 1):
            raise ValueError('Original mentor answer body')
        return dict(target=struct.unpack_from('>Q', payload)[0], accepted=bool(payload[33]),
                    reason=struct.unpack_from('>i', payload, 34)[0])
    if kind == 0x714:
        if payload:
            raise ValueError('Mentor search body must be empty')
        return {}
    if kind == 0x71b:
        if len(payload) != 17:
            raise ValueError('Mentor summon body')
        destination, x, y, z, board = struct.unpack('>ifffB', payload)
        from els_server.storage.local_state import validate_location
        validate_location(destination, board, 0, (x, y, z))
        return dict(destination=destination, xyz=(x, y, z), board=board)
    if kind == 0x71f:
        if len(payload) != 35 or payload[0] not in (0, 1) or payload[-1] not in (0, 1):
            raise ValueError('Mentor summon consent body')
        return dict(accepted=bool(payload[0]), echo=payload[1:])
    raise ValueError('Unknown mentor request')


def message(kind, payload):
    return Event(0x201, kind=kind, payload=payload)


def public_info(row):
    # DTO+29: online. +2A: break-unlock timestamp, parsed by 21B33A0.
    # +4A: public arena rank; +4C: this peer is the student (21AD170).
    # +4D: native class code; 31EFB20 displays its remainder modulo1000.
    return (struct.pack('>QB', row['uid'], row['level']) + wstring(row['name'])
            + bytes((int(row['online']),)) + wstring(row['unlock_at'])
            + struct.pack('>HBi', row['rank'], int(row['is_student']), row['unit_class']))


def acknowledgement(kind, result=0, text=''):
    if kind not in (0x1e4, 0x1e8, 0x714):
        raise ValueError('Unknown mentor acknowledgement')
    return message(kind + 1, i32(result) + (b'' if kind == 0x714 else wstring(text)))


def invitation(row):
    # 21ADE50 reads only DB5210. There is no trailing integer vector.
    return message(0x1ea, public_info(row))


def answer(target, row, accepted, reason=0):
    return message(0x1eb, struct.pack('>Q', target) + public_info(row)
                   + bytes((int(accepted),)) + i32(reason))


def declined(target, reason):
    return message(0x1eb, struct.pack('>Q', target) + EMPTY_ANSWER_INFO + b'\0' + i32(reason))


def partner(row, *, notify=False):
    # The bool and separate UID are read but the current UI copies DB5210.
    return message(0x1e7, bytes((int(notify),)) + struct.pack('>Q', row['uid']) + public_info(row))


def removed(target, text):
    # Second string clears the actor's reenrollment time under the approved rule.
    return message(0x1e6, struct.pack('>Q', target) + wstring(text) + wstring(''))


def role(value):
    if value not in (0, 1, 2):
        raise ValueError('Native mentor role')
    return message(0x717, i32(value))


def search_notice(character, channel=1):
    # 1227770 routes716 to12401B0. The native chat manager supplies the
    # localized type12 text and clickable name;87 is a different contract.
    return message(0x716, wstring(character['name'])
                   + struct.pack('>iiH', character['level'], character['unit_class'], channel))


def summon_ack(result=0):
    return message(0x71c, i32(result))


def summon_notice(location, nonce):
    # 21B0CE0 retains the final QQ/bool verbatim;21B1270 echoes them.
    # They are consent correlation, never client authority for a destination.
    return message(0x71d, struct.pack('>ifffB', location['map'], *location['xyz'], location['board'])
                   + struct.pack('>QQB', nonce >> 64, nonce & (2**64-1), 0))


def summoned(location, result=0, details=(0, 0, 0, 0)):
    # C50240, invoked by the original StateField+160 consumer30DAA50.
    return message(0x720, struct.pack('>iifffB4i', result, location['map'],
                   *location['xyz'], location['board'], *details))


def summon_result(accepted):
    return message(0x723, bytes((int(accepted),)))


def summon_error(result):
    return message(0x724, i32(result))
