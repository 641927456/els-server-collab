"""Pinned DX11 crafting (198/199) wire formats; no purchase route enabled.

Recipe authorization, material selection/consumption, output probabilities and
limit reset rules must be verified before using these codecs in a transaction.
"""
from dataclasses import dataclass
import struct

from els_server.domain.fashion_state import record, empty_record


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Manufacture integer range/type')
    return value


@dataclass(frozen=True)
class ManufactureRequest:
    recipe_id: int
    quantity: int
    selected_uid: int
    auxiliary_uids: tuple[int, ...]


def manufacture_request(payload):
    """235BFA0: i32 recipe, i32 quantity, i64 selection, set<i64>.

    The UI initializes selected_uid to -1 and excludes it from the auxiliary
    set (2315F00). The precise auxiliary selection policy is not yet recovered.
    Five entries is a local bound matching the five UI candidates, not a
    claim about every retail crafting feature.
    """
    if type(payload) is not bytes or len(payload) < 20:
        raise ValueError('Manufacture request size/type')
    recipe, quantity, selected, count = struct.unpack_from('>iiqI', payload)
    if count > 5 or len(payload) != 20 + 8 * count:
        raise ValueError('Manufacture request set length')
    _integer(recipe, 1, 2**31-1)
    _integer(quantity, 1, 2**31-1)
    if selected != -1:
        _integer(selected, 1, 2**63-1)
    uids = struct.unpack_from('>' + 'q' * count, payload, 20)
    if (any(uid <= 0 for uid in uids) or selected in uids
            or tuple(sorted(set(uids))) != uids):
        raise ValueError('Manufacture request UID set')
    return ManufactureRequest(recipe, quantity, selected, uids)


def manufacture_ack(*, result, rewards, changes, ed, profession_xp,
                    limit_id, limit_value):
    """2316F70: result, reward map, absolute ED, DD46E0 records, three i32s.

    XP is a delta (2DF8F70). A positive limit_id updates item-manager+518;
    limit_value is the absolute used count at value+4. Native2319000 subtracts
    it from the maximum at value+0. Reset timing and ownership scope remain
    unverified. Local collection bounds protect this encoder only.
    """
    _integer(result, -(2**31), 2**31-1)
    _integer(ed, 0, 2**63-1)
    _integer(profession_xp, 0, 2**31-1)
    _integer(limit_id, 0, 2**31-1)
    _integer(limit_value, 0, 2**31-1)
    if type(rewards) is not dict or len(rewards) > 512:
        raise ValueError('Manufacture reward map')
    if not isinstance(changes, (tuple, list)) or len(changes) > 512:
        raise ValueError('Manufacture inventory changes')
    reward_rows = []
    for template, count in rewards.items():
        _integer(template, 1, 2**31-1)
        _integer(count, 1, 2**31-1)
        reward_rows.append((template, struct.pack('>ii', template, count)))
    slots, records = set(), []
    for position, item in changes:
        group, slot = position
        _integer(group, 0, 255)
        _integer(slot, 0, 32767)
        if (group, slot) in slots:
            raise ValueError('Duplicate manufacture inventory slot')
        slots.add((group, slot))
        if item is not None and (item['group'], item['slot']) != (group, slot):
            raise ValueError('Manufacture inventory slot mismatch')
        records.append(empty_record(group, slot) if item is None else record(item))
    return (struct.pack('>iI', result, len(reward_rows))
            + b''.join(raw for _, raw in sorted(reward_rows))
            + struct.pack('>QI', ed, len(records)) + b''.join(records)
            + struct.pack('>iii', profession_xp, limit_id, limit_value))
