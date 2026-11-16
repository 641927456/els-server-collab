"""Original relation summon request, consent and scene transition."""
import struct

from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import validate_location


def request(payload):
    if len(payload) != 17:
        raise ValueError('Relation summon location')
    map_id, x, y, z, board = struct.unpack('>ifffB', payload)
    validate_location(map_id, board, 0, (x, y, z))
    return map_id


def consent(payload):
    if len(payload) != 35 or payload[0] not in (0, 1):
        raise ValueError('Relation summon consent')
    return bool(payload[0]), payload[1:]


def ack(result=0):
    return Event(0x201, kind=0x40b, payload=struct.pack('>i', result))


def invitation(location, nonce):
    # BB4930 stores this location and opaque token; BB5120 echoes both.
    body = struct.pack('>ifffB', location['map'], *location['xyz'], location['board'])
    return Event(0x201, kind=0x40c, payload=body + nonce.bytes + b'\0')


def outcome(accepted):
    return Event(0x201, kind=0x412, payload=bytes((accepted,)))


def arrive(location):
    # CX2StateField+158 -> 30D9E20 -> C50240, also used by mentor 720.
    from els_server.protocol.mentor_messages import summoned
    return Event(0x201, kind=0x40f, payload=summoned(location).payload)
