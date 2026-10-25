"""EC/ED merchant sale DTOs, paired with native 2C5C600/2D31CB0.

The request starts with a native random byte string (4..16 bytes), then a
vector of UID/count pairs and an XOR-obfuscated merchant context ID.
Prices are never supplied by the client. ED carries absolute money, inventory
changes, then sold rows for the native repurchase history.
"""
import struct
from els_server.domain.fashion_state import record, empty_record

MAX_ITEMS = 100
MERCHANT_XOR = 0xca4da809


def request(payload):
    if not isinstance(payload, bytes) or len(payload) < 28:
        raise ValueError('Sale request length')
    noise_size = struct.unpack_from('>I', payload)[0]
    if not 4 <= noise_size <= 16 or len(payload) < noise_size+12:
        raise ValueError('Sale random prefix bound')
    offset = 4 + noise_size
    count = struct.unpack_from('>I', payload, offset)[0]
    if not 1 <= count <= MAX_ITEMS or len(payload) != offset + 8 + 12*count:
        raise ValueError('Sale request vector')
    entries = [struct.unpack_from('>Qi', payload, offset + 4 + 12*n) for n in range(count)]
    merchant = struct.unpack_from('>I', payload, offset + 4 + 12*count)[0] ^ MERCHANT_XOR
    if not 0 < merchant < 2**31 or len({u for u, q in entries}) != count:
        raise ValueError('Sale merchant or duplicate UID')
    if any(not 0 < uid < 2**63 or quantity <= 0 for uid, quantity in entries):
        raise ValueError('Sale UID/count bound')
    return entries, merchant


def acknowledgement(ed, changes=(), sold=(), result=0):
    if type(ed) is not int or not 0 <= ed < 2**63:
        raise ValueError('Sale balance bound')
    if len(changes) > MAX_ITEMS or len(sold) > MAX_ITEMS:
        raise ValueError('Sale response bound')
    wire = (struct.pack('>iQI', result, ed, len(changes)) +
            b''.join(empty_record(*p) if item is None else record(item) for p, item in changes) +
            struct.pack('>I', len(sold)) + b''.join(record(i) for i in sold))
    # Event payload length and secure-frame length are uint32. Match the local
    # codec's 1 MiB frame budget, leaving room for event/crypto headers; two
    # 100-row native vectors can legitimately exceed 64 KiB.
    if len(wire) > 1024*1024-128:
        raise ValueError('Sale response exceeds frame budget')
    return wire
