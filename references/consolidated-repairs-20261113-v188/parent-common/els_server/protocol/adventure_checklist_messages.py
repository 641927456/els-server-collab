"""Native D00 restore, D01 category replacement and D02 acknowledgement."""

import struct

from els_server.protocol.protocol_codec import Event


def request(payload):
    if len(payload) < 8:
        raise ValueError('Truncated adventure checklist request')
    category, count = struct.unpack_from('>iI', payload)
    if category not in (1, 2, 3) or count > 100 or len(payload) != 8 + 4 * count:
        raise ValueError('Invalid adventure checklist category or count')
    ids = struct.unpack_from(f'>{count}i', payload, 8)
    if any(value <= 0 for value in ids) or len(set(ids)) != count:
        raise ValueError('Invalid adventure checklist favorite IDs')
    return category, ids


def _categories(favorites):
    return struct.pack('>I', len(favorites)) + b''.join(
        struct.pack(f'>iI{len(ids)}i', category, len(ids), *ids)
        for category, ids in sorted(favorites.items())
    )


def initialization(favorites):
    return Event(0x201, kind=0xd00, payload=_categories(favorites))


def acknowledgement(favorites, *, result=0):
    return Event(0x201, kind=0xd02, payload=struct.pack('>i', result) + _categories(favorites))
