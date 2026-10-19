"""DX11 inventory management writers, paired with native consumer evidence."""
import struct
from els_server.domain.fashion_state import record, empty_record


def sort_ack(items=(), result=0):
    # C4F050: result followed by DB3BF0 inventory vector (also BD7).
    return struct.pack('>iI', result, len(items)) + b''.join(record(i) for i in items)


def category_sort_request(payload):
    # Original2353FD0 /370 writes one signed SORT_TYPE, unlike ice-window BD6.
    if not isinstance(payload, bytes) or len(payload) != 4:
        raise ValueError('Category sort request size')
    return struct.unpack('>i', payload)[0]


def category_sort_ack(category, items=(), result=0):
    # Original2275C00 /371: category, vector<UID>, result, DD46E0 records.
    # 1987260 removes absent UIDs, orders retained UIDs, then applies records.
    # 1985130 increments the slot index even for an absent UID. Zero entries
    # preserve holes on receipt replay after a later move/discard; do not
    # compact the client's current state without committing the same move.
    by_slot = {item['slot']: item['uid'] for item in items}
    uids = [by_slot.get(slot, 0) for slot in range(max(by_slot, default=-1)+1)]
    return (struct.pack('>iI', category, len(uids)) +
            b''.join(struct.pack('>Q', uid) for uid in uids) +
            struct.pack('>iI', result, len(items)) + b''.join(record(i) for i in items))


def lock_request(payload):
    # 23551B0 / 663: Q UID, signed short days, int action, bool cheat.
    if len(payload) != 15:
        raise ValueError('Item lock request size')
    uid, days, action, cheat = struct.unpack('>QhiB', payload)
    if not 1 <= uid < 2**63 or action not in (0, 1) or cheat != 0:
        raise ValueError('Item lock request fields')
    if (action == 0 and not 1 <= days <= 30) or (action == 1 and days != 0):
        raise ValueError('Item lock duration/action')
    return uid, days, action


def lock_ack(ed, action=0, result=0):
    # 2279EB0 / 664: result, absolute ED, action (0 locked / 1 unlocked).
    return struct.pack('>iQi', result, ed, action)


def seal_request(payload):
    # Original2356B31/2356B42: target instance UID, then stamp instance UID.
    if not isinstance(payload, bytes) or len(payload) != 16:
        raise ValueError('Seal request length')
    target, stamp = struct.unpack('>QQ', payload)
    if target == stamp or any(not 1 <= uid < 2**63 for uid in (target, stamp)):
        raise ValueError('Seal request identities')
    return target, stamp


def unseal_request(payload):
    # Original2351851: one UID. The batch UI sends individual272 requests.
    if not isinstance(payload, bytes) or len(payload) != 8:
        raise ValueError('Unseal request length')
    uid, = struct.unpack('>Q', payload)
    if not 1 <= uid < 2**63:
        raise ValueError('Unseal request identity')
    return uid


def seal_ack(changes=(), result=0):
    # 271 and273 both use C4F050: signed result, full inventory vector.
    return struct.pack('>iI', result, len(changes)) + b''.join(
        record(item) if item else empty_record(*position) for position, item in changes)


def decompose_request(payload):
    if len(payload) < 13:
        raise ValueError('Decomposition request size')
    count, = struct.unpack_from('>I', payload)
    if not 1 <= count <= 100 or len(payload) != 5 + count * 8 or payload[-1] != 0:
        raise ValueError('Decomposition request fields')
    uids = struct.unpack_from('>' + 'Q' * count, payload, 4)
    if len(set(uids)) != count or any(not 1 <= uid < 2**63 for uid in uids):
        raise ValueError('Decomposition UID list')
    return uids


def decompose_ack(changes=(), rewards=None, result=0):
    rewards = rewards or {}
    # 22793A0: result, profession flag, reward counts, records, profession XP,
    # bonus reward counts. The ordinary dismantle path has no profession bonus.
    return (struct.pack('>iBI', result, 0, len(rewards)) +
            b''.join(struct.pack('>ii', t, n) for t, n in sorted(rewards.items())) +
            struct.pack('>I', len(changes)) +
            b''.join(record(i) if i else empty_record(*p) for p, i in changes) + bytes(8))
