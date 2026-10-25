"""Native EA/EB purchase and 567/568 repurchase records."""
import struct
from els_server.domain.fashion_state import record


def purchase_request(payload):
    if not isinstance(payload, bytes) or len(payload) < 19:
        raise ValueError('Merchant purchase length')
    flag, mode, count = struct.unpack_from('>BHI', payload)
    if flag != 0 or mode != 0 or not 1 <= count <= 36 or len(payload) != 11+8*count:
        raise ValueError('Unsupported merchant purchase mode/vector')
    entries = [struct.unpack_from('>ii', payload, 7+8*n) for n in range(count)]
    merchant = struct.unpack_from('>i', payload, 7+8*count)[0]
    if merchant <= 0 or len({t for t, q in entries}) != count or any(t <= 0 or not 1 <= q <= 99 for t, q in entries):
        raise ValueError('Merchant purchase identity/count')
    return entries, merchant


def purchase_ack(ed, changes=(), result=0):
    # 1B19E30: result, absolute ED, absolute VP, inventory vector.
    return struct.pack('>iQiI', result, ed, 0, len(changes))+b''.join(record(i) for i in changes)


def repurchase_request(payload):
    # Parse only the bounded prefix. The complete variable-length record is
    # compared byte-for-byte with the authoritative sale instance in storage.
    if not isinstance(payload, bytes) or not 332 <= len(payload) <= 2048:
        raise ValueError('Repurchase record length')
    index = struct.unpack_from('>i', payload)[0]
    quantity = struct.unpack_from('>i', payload, 20)[0]
    merchant = struct.unpack_from('>i', payload, len(payload)-4)[0]
    if not 0 <= index < 8 or not 1 <= quantity <= 10000 or merchant <= 0:
        raise ValueError('Repurchase index/count/context')
    return index, quantity, merchant, payload[4:-4]


def repurchase_ack(ed, index=0, quantity=0, changes=(), result=0):
    return struct.pack('>iiQiiI', result, index, ed, 0, quantity, len(changes))+b''.join(record(i) for i in changes)
