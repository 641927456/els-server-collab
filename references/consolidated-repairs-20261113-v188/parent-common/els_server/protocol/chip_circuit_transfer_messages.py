"""Original D2E/D2F chip/circuit transfer wire, with no ED field or tail."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.equipment_reforge_transfer_messages import _changes_wire


def request(payload):
    if type(payload) is not bytes or len(payload) != 16:
        raise ValueError('Chip/circuit transfer needs two original UIDs')
    source, target = struct.unpack('>QQ', payload)
    if not (0 < source < 2**63 and 0 < target < 2**63) or source == target:
        raise ValueError('Chip/circuit transfer distinct persistent UIDs')
    return source, target


def acknowledgement(source, target, changes=(), result=0):
    request(struct.pack('>QQ', source, target))
    if type(result) is not int or not -2**31 <= result < 2**31:
        raise ValueError('Chip/circuit transfer result')
    if result != 0 and changes:
        raise ValueError('Rejected transfer cannot update inventory')
    vector, identities = _changes_wire(changes)
    if result == 0 and identities != {source, target}:
        raise ValueError('Successful transfer needs both exact owned records')
    payload = struct.pack('>iQQ', result, source, target) + vector
    if len(payload) + 64 > 1024 * 1024:
        raise ValueError('Transfer exceeds existing frame bound')
    return Event(0x201, kind=0xd2f, payload=payload)
