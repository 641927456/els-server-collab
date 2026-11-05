"""Original 518 attendance wire messages; not yet enabled in session dispatch.

Evidence: attendance518-2026-v1/state-wire-check.json, pinned c8815e00 image.
E1DCA0 dispatches BA5/BA7/BA9; 2BE3320 reads Qii. EE2760 and
EE28F0 consume the daily and weekly bits, EE50B0 uses purchases remaining.
The first BA5 qword feeds EE5650's date conversion: retain its raw value until
the server/client epoch and daily boundary are independently established.
These codecs authorize no participation, rewards, ED debit or database writes.
"""
import struct
from dataclasses import dataclass
from els_server.protocol.protocol_codec import Event


def _integer(value, bits, *, signed=False):
    lower = -(1 << (bits - 1)) if signed else 0
    upper = (1 << (bits - 1)) if signed else (1 << bits)
    if type(value) is not int or not lower <= value < upper:
        raise ValueError('签到协议整数超出原始字段范围')
    return value


@dataclass(frozen=True)
class AttendanceState:
    daily_mask: int
    weekly_mask: int
    purchased_count: int

    def wire(self):
        # Wire widths, not eligibility limits. The business layer must enforce
        # the selected campaign's 42 days and maximum 21 purchases.
        return struct.pack('>Qii', _integer(self.daily_mask, 64),
                           _integer(self.weekly_mask, 32, signed=True),
                           _integer(self.purchased_count, 32, signed=True))


def state_notice(anchor_value, state):
    """BA5: raw date anchor followed by the original 16-byte state."""
    return Event(0x201, kind=0xba5,
                 payload=struct.pack('>Q', _integer(anchor_value, 64)) + state.wire())


def weekly_reward_request(payload):
    """BA6 / 11128F0: exactly one signed 32-bit index."""
    if type(payload) is not bytes or len(payload) != 4:
        raise ValueError('签到奖励请求长度无效')
    return struct.unpack('>i', payload)[0]


def purchase_request(payload):
    """BA8 / EE45B0 -> 7E9610: empty original request."""
    if type(payload) is not bytes or payload:
        raise ValueError('签到补签请求长度无效')


def weekly_reward_reply(result, state):
    return Event(0x201, kind=0xba7,
                 payload=struct.pack('>i', _integer(result, 32, signed=True)) + state.wire())


def purchase_reply(result, ed, state):
    """BA9 currency is the updater's absolute input, not an ED deduction."""
    return Event(0x201, kind=0xba9,
                 payload=struct.pack('>iQ', _integer(result, 32, signed=True),
                                     _integer(ed, 64)) + state.wire())
