"""9F4..9F9 and 855 normal storage bodies; no developer override authority."""
import math
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.tenebros_capacity_messages import integer, capacities


def save_request(payload):
    if type(payload) is not bytes or len(payload) != 44:
        raise ValueError('Tenebros save body')
    uid, part, slot, count = struct.unpack_from('>QiiI', payload)
    integer(uid, 1, 2**63-1); integer(part, 0, 3); integer(slot, 0, 5)
    if count != 3:
        raise ValueError('Tenebros three native probabilities')
    rows = [struct.unpack_from('>if', payload, 20+8*n) for n in range(3)]
    if [r[0] for r in rows] != [0, 1, 2]:
        raise ValueError('Tenebros canonical probability keys')
    values = tuple(r[1] for r in rows)
    if any(not math.isfinite(v) or not v.is_integer() or not 0 <= v <= 100 for v in values) or sum(values) != 100:
        raise ValueError('Tenebros normal integer probability domain')
    return uid, part, slot, tuple(int(v) for v in values)


def load_request(payload):
    if type(payload) is not bytes or len(payload) != 25:
        raise ValueError('Tenebros load body')
    uid, part, line, slot, developer, override = struct.unpack('>QiiiBi', payload)
    integer(uid, 1, 2**63-1); integer(part, 0, 3); integer(line, 0, 2); integer(slot, 0, 5)
    if developer != 0 or override != 0:
        raise ValueError('Tenebros developer override refused')
    return uid, part, line, slot


def confirm_request(payload):
    if type(payload) is not bytes or len(payload) != 8:
        raise ValueError('Tenebros confirm body')
    return integer(struct.unpack('>Q', payload)[0], 1, 2**63-1)


def cancel_request(payload):
    if type(payload) is not bytes or payload:
        raise ValueError('Tenebros 855 has an empty body')


def storage_row(extra, options):
    integer(extra, 0, 3)
    if type(options) not in (tuple, list) or len(options) != 6:
        raise ValueError('Tenebros six native storage cells')
    values = tuple(integer(v, 0, 2**31-1) for v in options)
    if any(values[3+extra:]):
        raise ValueError('Tenebros occupied locked storage cell')
    return struct.pack('>iI6i', extra, 6, *values)


def state(extras, options):
    extras = capacities(extras)
    if type(options) not in (list, tuple) or len(options) != 4:
        raise ValueError('Tenebros four storage parts')
    return Event(0x201, kind=0x9f1, payload=struct.pack('>I', 4)+b''.join(
        struct.pack('>i', part)+storage_row(extras[part], options[part]) for part in range(4)))


def records(changes):
    rows = tuple(changes)
    if len(rows) > 64 or len({tuple(pos) for pos, item in rows}) != len(rows):
        raise ValueError('Tenebros changed positions')
    if not rows:
        return struct.pack('>I', 0)
    from els_server.domain.fashion_state import record, empty_record
    out = []
    for (group, slot), item in rows:
        integer(group, 1, 31); integer(slot, 0, 32767)
        if item is not None and (item['group'], item['slot']) != (group, slot):
            raise ValueError('Tenebros change record position')
        out.append(empty_record(group, slot) if item is None else record(item))
    return struct.pack('>I', len(out))+b''.join(out)


def save_ack(ed=0, extra=0, options=(0,)*6, changes=(), *, result=0):
    return Event(0x201, kind=0x9f5, payload=struct.pack('>iQ',
        integer(result, -2**31, 2**31-1), integer(ed, 0, 2**63-1))+
        storage_row(extra, options)+records(changes))


def load_ack(ed=0, option_id=0, extra=0, options=(0,)*6, changes=(), *, result=0):
    return Event(0x201, kind=0x9f7, payload=struct.pack('>iQi',
        integer(result, -2**31, 2**31-1), integer(ed, 0, 2**63-1),
        integer(option_id, 0, 2**31-1))+storage_row(extra, options)+records(changes))


def confirm_ack(opaque_q=0, changes=(), *, result=0):
    # The consumer parses this Q but does not use it as an ED authority.
    return Event(0x201, kind=0x9f9, payload=struct.pack('>iQ',
        integer(result, -2**31, 2**31-1), integer(opaque_q, 0, 2**63-1))+records(changes))
