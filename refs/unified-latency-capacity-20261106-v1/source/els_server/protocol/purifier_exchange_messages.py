"""Finite native223 exchange and complete224; reuse full inventory records."""
from dataclasses import dataclass
import struct
from els_server.domain.fashion_state import record, empty_record


@dataclass(frozen=True)
class ExchangeRequest:
    house: int
    source_uid: int
    source: int
    source_quantity: int
    destination: int
    exchange_type: int
    quantity: int
    native_flag: int
    native_index: int


def request(payload):
    # 1107AA0 primitive serializers are network order, not the packed-memory
    # little-endian DTO used to describe the original call stack.
    if not isinstance(payload, bytes) or len(payload) != 37:
        raise ValueError('Native exchange request length')
    r = ExchangeRequest(*struct.unpack('>iQiiiiiBi', payload))
    # The confirmed native manual-select UI supplies these exact two trailing
    # constants. Their other modes are outside this finite route.
    if (r.house != 40272 or r.source_uid != 0 or r.source != 136115
            or r.exchange_type != 3 or r.native_flag != 1 or r.native_index != 0
            or r.quantity != 1):
        raise ValueError('Unsupported native exchange mode')
    return r


def acknowledgement(ed, changes=(), rewards=(), result=0, exchange_type=3):
    # 10FFA70: result, full-item vector, result map, bool, byte, Q, Q.
    # 22A9A00 applies the final Q to the same character+D8 ED field as EB's
    # FEB6E0. Item-only selection has no currency reward (penultimate Q=0).
    if type(ed) is not int or not 0 <= ed < 2**63 or exchange_type != 3:
        raise ValueError('Exchange absolute ED/type')
    if result not in (0, -1) or len(changes) > 72 or len(rewards) > 1:
        raise ValueError('Exchange acknowledgement bound')
    rows = b''.join(empty_record(*pos) if item is None else record(item)
                    for pos, item in changes)
    result_map = b''.join(struct.pack('>ii', t, n) for t, n in rewards)
    return (struct.pack('>iI', result, len(changes)) + rows
            + struct.pack('>I', len(rewards)) + result_map
            + struct.pack('>BBQQ', 1, exchange_type, 0, ed))
