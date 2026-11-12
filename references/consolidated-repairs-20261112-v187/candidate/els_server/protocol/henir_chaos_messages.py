"""Current Chaos progress and reward-selection messages."""
import struct

from els_server.protocol.protocol_codec import Event


SELECT = 0xcd6
REWARD_POWER_MAGIC = 0x48435031


def request(payload, owner):
    if len(payload) == 4:
        return struct.unpack('>i', payload)[0], None
    if len(payload) == 20:
        template, magic, actor, power = struct.unpack('>iIQi', payload)
        if magic == REWARD_POWER_MAGIC and actor == owner and power >= 0:
            return template, power
    raise ValueError('Chaos selection body or reward-room combat power')


def selected(result):
    return Event(0x201, kind=0xcd7, payload=struct.pack('>i', result))


def progress(state):
    # BF4B10 receives an i32 status, progress index, grade and vector<int>.
    if state is None:
        return Event(0x201, kind=0xcd4, payload=struct.pack('>iiiI',0,-1,0,0))
    return Event(0x201, kind=0xcd4, payload=struct.pack(
        '>iiiI'+'i'*len(state.normal), 0, state.completed, state.grade, len(state.normal), *state.normal,
    ))


def grade(value, increase):
    # C2853C stores iRewardLevel and iLevelUpResult for RewardLevelChanged.
    return Event(0x201, kind=0xcd5, payload=struct.pack('>ii', value, increase))
