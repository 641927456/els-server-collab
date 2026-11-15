"""Current 707/708, 9AE/9AF/9B0 fields; unknown fields explicitly zero policy."""
import struct
from els_server.domain.fashion_state import record, empty_record


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Flask integer range/type')
    return value


def request(payload):
    if type(payload) is not bytes or len(payload) != 44 or struct.unpack_from('>I', payload)[0] != 5:
        raise ValueError('Flask five UID vector size')
    values = struct.unpack_from('>5Q', payload, 4)
    if len(set(values)) != 5:
        raise ValueError('Flask duplicate slot UID')
    for value in values:
        integer(value, 1, 2**63-1)
    return values


def nested(state):
    # E0's retail semantic/epoch is unproven. Zero is an explicit local opaque
    # value; the trusted CN reset period is stored only in the SQL ledger.
    return struct.pack('>iQQ', integer(state['used'], 0, 7),
                       integer(state['gauge'], 0, 2**63-1), 0)


def rewards_wire(rewards):
    if type(rewards) is not dict or len(rewards) > 16:
        raise ValueError('Flask reward map bound')
    rows = []
    for template, quantity in sorted(rewards.items()):
        rows.append(struct.pack('>ii', integer(template, 1, 2**31-1),
                                integer(quantity, 1, 2**31-1)))
    return struct.pack('>I', len(rows)) + b''.join(rows)


def changes_wire(changes):
    if not isinstance(changes, (list, tuple)) or len(changes) > 512:
        raise ValueError('Flask inventory vector bound')
    seen, rows = set(), []
    for position, item in changes:
        group, slot = position
        integer(group, 0, 255)
        integer(slot, 0, 32767)
        if (group, slot) in seen or item is not None and (item['group'], item['slot']) != (group, slot):
            raise ValueError('Flask inventory position mismatch')
        seen.add((group, slot))
        rows.append(empty_record(group, slot) if item is None else record(item))
    return struct.pack('>I', len(rows)) + b''.join(rows)


def acknowledgement(kind, *, result=0, ed=0, state=None, rewards=None, changes=(), xp=0):
    state = dict(used=0, gauge=0) if state is None else state
    rewards = {} if rewards is None else rewards
    header = struct.pack('>i', integer(result, -(2**31), 2**31-1))
    if kind == 0x707:
        return (header + struct.pack('>iQ', 0, integer(ed, 0, 2**63-1))
                + rewards_wire(rewards) + changes_wire(changes) + nested(state)
                + struct.pack('>i', integer(xp, 0, 2**31-1)))
    if kind == 0x9ae:
        if xp:
            raise ValueError('Gauge claim must not grant XP')
        return header + nested(state) + rewards_wire(rewards) + changes_wire(changes)
    raise ValueError('Flask response request kind')


def notification(state):
    return nested(state) + struct.pack('>i', 7)
