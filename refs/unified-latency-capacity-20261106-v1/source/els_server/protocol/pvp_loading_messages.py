"""Current native ordinary PvP loading, without changing an actor or match.

316C060 -> C4FE60 -> C66AD0 sends progress plus zero, not a claimed level.
316C150 consumes all three ACK integers; 316C350 consumes UID + progress.
316C540/C4FF50 consumes state + D9DDB0 slots + i32 (ordinary dungeon ID0).
97 is the intruder-position chain and is not a required ordinary-start ACK.
"""
import struct
from els_server.protocol.protocol_codec import Event


def progress_request(payload):
    if type(payload) is not bytes or len(payload) != 8:
        raise ValueError('PvP loading request length')
    progress, zero = struct.unpack('>ii', payload)
    if not 0 <= progress <= 100 or zero != 0:
        raise ValueError('PvP loading request fields')
    return progress


def progress_ack(progress, result=0):
    if type(progress) is not int or not 0 <= progress <= 100:
        raise ValueError('PvP loading ACK progress')
    if type(result) is not int or not -(2**31) <= result < 2**31:
        raise ValueError('PvP loading ACK result')
    return Event(0x201, kind=0x92, payload=struct.pack('>iiI', result, progress, 0))


def progress_notice(uid, progress):
    if type(uid) is not int or not 1 <= uid < 2**63:
        raise ValueError('PvP loading actor')
    progress_ack(progress)
    return Event(0x201, kind=0x93, payload=struct.pack('>Qi', uid, progress))


def play_start(admitted_slots):
    """Reuse the exact two complete native member slots captured at admission.

    Only SS_LOADING4 becomes SS_PLAY5. The producer must bind these private
    bytes to the unchanged two current actors and both monotonic load100s.
    This codec cannot establish that authorization from a client payload.
    """
    if type(admitted_slots) is not tuple or len(admitted_slots) != 2:
        raise ValueError('PvP two admitted slots')
    slots = []
    for index, slot in enumerate(admitted_slots):
        expected = bytes((index, 4, int(index == 0), 1, 0, 0)) + struct.pack('>iI', index, 1)
        if type(slot) is not bytes or len(slot) <= len(expected)+8 or not slot.startswith(expected):
            raise ValueError('PvP admitted native slot')
        if slot[-8:] != bytes(8):
            raise ValueError('PvP alternate-member/slot tail')
        slots.append(slot[:1] + b'\5' + slot[2:])
    return Event(0x201, kind=0x96, payload=b'\5' + struct.pack('>I', 2) + b''.join(slots) + struct.pack('>i', 0))
