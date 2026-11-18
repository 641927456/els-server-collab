"""Original B37/B38 sort-position pins (separate from timed item locks)."""
import struct
from els_server.protocol.protocol_codec import Event

BAGS = (1, 2, 3, 4, 5, 6, 7, 21, 27)


def request(payload):
    # 2275EF0 -> 2354330: action byte, category i32, slot i32, zero u64.
    if len(payload) != 17:
        raise ValueError('Sort pin request size')
    action, group, slot, reserved = struct.unpack('>BiiQ', payload)
    if action not in (1, 2) or group not in BAGS or slot < 0 or reserved:
        raise ValueError('Sort pin request fields')
    return action, group, slot


def pin_map(pins):
    # DB6F10/DD7C30: map<int, set<int>>, both counts u32.
    return struct.pack('>I', len(pins)) + b''.join(
        struct.pack('>iI', group, len(slots)) +
        b''.join(struct.pack('>i', slot) for slot in sorted(slots))
        for group, slots in sorted(pins.items()))


def acknowledgement(pins=None, action=0, group=0, slot=-1, result=0):
    # 234B780 -> 2276010 replaces the complete client pin map.
    return Event(0x201, kind=0xb38, payload=struct.pack('>iBii', 21 if result == -1 else result, action, group, slot)
                 + pin_map(pins or {}))
