"""Task166210 wire projection; does not accept, complete or grant the task.

The caller supplies account-scoped, authenticated progress for the accepted
daily task; the wire owner is the currently authenticated character UID.
Period rollover must not replace an unclaimed completed task. Online count
conversion remains in the authoritative type102 session adapter.
"""
import struct
from els_server.storage.character_schema import character_uid
from els_server.protocol.protocol_codec import Event
from els_server.protocol import quest_messages

QUEST_ID = 166210
CLEAR_SUBQUEST = 1000005
ONLINE_SUBQUEST = 165620


def active_record(*, owner_uid, clears, online_count, online_complete):
    """Render verified counters without inferring online units or eligibility.

    Online_count and online_complete must come from a verified type102 adapter,
    not elapsed wall clock or any client-supplied packet.
    """
    for value, maximum, name in ((clears, 5, 'clears'),
                                 (online_count, 65535, 'online_count')):
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError('Invalid '+name)
    if type(online_complete) is not bool:
        raise ValueError('Online completion must be authoritative boolean')
    # DD6E80 DTO+4 -> DFC350 runtime+8 ->3037260 role-UID gate.
    # Actual accepted_at is stored metadata, never this native owner field.
    return (struct.pack('>iQQI', QUEST_ID, character_uid(owner_uid), 0, 2)
            + struct.pack('>iHB', CLEAR_SUBQUEST, clears, int(clears == 5))
            + struct.pack('>iHB', ONLINE_SUBQUEST, online_count, int(online_complete)))


def accepted(**state):
    return Event(0x201, kind=0xf0, payload=active_record(**state)+bytes(12))


def progress(**state):
    return Event(0x201, kind=0xf3, payload=struct.pack('>I', 1)+active_record(**state))


def claim_request(payload):
    request = quest_messages.request(0xf4, payload)
    if request['quest'] != QUEST_ID:
        raise ValueError('Not the selected attendance task')
    return request


def reward_unavailable(character, location, slots, balances, items):
    """Full existing F5 shape, no successful completion record or item delta."""
    return quest_messages.reward_ack(
        QUEST_ID, character, location, slots, balances, items,
        result=quest_messages.QUEST_REWARD_UNAVAILABLE, completed_at=0)
