"""Reviewed native9ED/9EE codec for the finite normal atomic consumer.

The request flag remains a raw verified 0/1 byte. This module neither interprets
its material mode nor chooses resulting reforge life, gauges or item sidecars.
"""
import struct
from els_server.protocol.protocol_codec import Event

RUNTIME_ENABLED = True


def _uid(value):
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError('Transfer item UID')
    return value


def request(payload):
    if not isinstance(payload, bytes) or len(payload) != 17:
        raise ValueError('Transfer request length/type')
    source, target, flag = struct.unpack('>QQB', payload)
    _uid(source); _uid(target)
    if source == target or flag not in (0, 1):
        raise ValueError('Transfer distinct items/raw flag')
    return source, target, flag


def _changes_wire(changes):
    from els_server.domain.bag_capacity import wire_limit
    from els_server.domain.equipment_requirements import catalog as requirements
    from els_server.domain.fashion_state import record, empty_record
    slots = set(requirements()[1].values())
    groups = (1, 2, 3, 4, 5, 6)
    limit = sum(wire_limit(g) for g in groups) + len(slots)
    if not isinstance(changes, (list, tuple)) or len(changes) > limit:
        raise ValueError('Transfer changed-record bound')
    positions = set(); identities = set(); records = []
    for entry in changes:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError('Transfer change pair')
        pos, item = entry
        if (not isinstance(pos, (list, tuple)) or len(pos) != 2
                or any(type(v) is not int for v in pos)):
            raise ValueError('Transfer changed position')
        group, slot = pos
        if not ((group in groups and 0 <= slot < wire_limit(group))
                or (group == 9 and slot in slots)):
            raise ValueError('Transfer changed slot outside local wire range')
        pos = tuple(pos)
        if pos in positions:
            raise ValueError('Duplicate transfer changed position')
        positions.add(pos)
        if item is None:
            records.append(empty_record(*pos))
        else:
            if (not isinstance(item, dict) or (item.get('group'), item.get('slot')) != pos
                    or type(item.get('uid')) is not int or item['uid'] in identities):
                raise ValueError('Transfer changed item identity/position')
            identities.add(item['uid'])
            records.append(record(item))
    return struct.pack('>I', len(records)) + b''.join(records), identities


def acknowledge(source, target, ed, changes=(), result=0):
    _uid(source); _uid(target)
    if source == target or type(ed) is not int or not 0 <= ed < 2**63:
        raise ValueError('Transfer acknowledgement identities/ED')
    if type(result) is not int or not -2**31 <= result < 2**31:
        raise ValueError('Transfer result')
    vector, identities = _changes_wire(changes)
    if result == 0 and not {source, target} <= identities:
        raise ValueError('Successful transfer needs both actual item records')
    if result != 0 and changes:
        raise ValueError('Rejected transfer must not change item records')
    payload = struct.pack('>iQQQ', result, source, target, ed) + vector
    # Existing frame decoder is bounded at 1 MiB. Fail before any future commit.
    if len(payload) + 64 > 1024 * 1024:
        raise ValueError('Transfer response exceeds local secure-frame bound')
    return Event(0x201, kind=0x9ee, payload=payload)
