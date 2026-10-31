"""Current 34B official real-player 1v1 admission encoding, not admission authority.

2D68DB0/2B4D8B0 read D9BCC0 and D9DDB0, then native state9 starts
XS_PVP_GAME. Finite ordinary slots select the existing D9D2F0 member reader;
alternate-member vectors, observers and NPCs remain empty. The caller must
freeze both real actors, native confirmations and peer transport before use.
"""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32, u32, wstring

# Exact m_AvailableMatchType contains MT_TEAM_1_ON_1 in the pinned current map
# table. Missing availability is not an allow-all rule; no selection policy here.
TEAM_MAPS = frozenset((1, 34, 67, 73, 169, 292, 347, 546, 1020, 1045, 1199, 1200))


def _integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError('PvP native room integer')
    return value


def room_info(room_uid, map_id, bootstrap_port):
    """Complete current D9BCC0; native ctor-zero fields retain their meanings.

    Shared base fields use the existing ordinary transport representation.
    PvP-specific +95/+97/+9B/+9D/+A1/+A3 are team mode0, official12,
    one kill, float300, actual/show world. No dungeon identity is substituted.
    """
    _integer(room_uid, 1, 2**63-1)
    _integer(map_id, 1, 32767)
    _integer(bootstrap_port, 1, 65535)
    if map_id not in TEAM_MAPS:
        raise ValueError('Unsupported current 1v1 map')
    data = b'\0' + struct.pack('>Q', room_uid) + u32(0) + wstring('Official1v1')
    # Current ROOM_STATE.RS_LOADING=4; public=true, no balance/password mode.
    data += b'\4\1\0' + wstring('') + b'\2\2'
    data += wstring('127.0.0.1') + struct.pack('>H', bootstrap_port) + wstring('')
    data += b'\0\0\0' + i32(12) + b'\1\0' + struct.pack('>fhh', 300, map_id, map_id)
    # +A5/+AD and all dungeon/special-system fields use native empty state.
    data += bytes(8) + i32(0) + b'\0' + i32(0) + bytes(2)
    data += bytes(8)*2 + i32(0) + b'\0'
    data += u32(0) + bytes(2) + i32(0) + bytes(2) + bytes(8) + u32(0)
    data += b'\0' + i32(0) + bytes(8)*2
    return data


def admission(members, room_uid, map_id, bootstrap_port, *, member_captures=None):
    """Encode precisely two already-confirmed real actors in red/blue order.

    This does not enqueue, choose an opponent/map, alter a phase or start a
    clock. Source/membership/lease and unchanged-input guards belong to flow.
    """
    from els_server.protocol.dungeon_messages import member
    if type(members) is not tuple or len(members) != 2 or members[0] is members[1]:
        raise ValueError('PvP exact two real members')
    ids = tuple(_integer(s.account.uid, 1, 2**63-1) for s in members)
    accounts = tuple(_integer(s.account.account_id, 1, 2**63-1) for s in members)
    if len(set(ids)) != 2 or len(set(accounts)) != 2:
        raise ValueError('PvP distinct account actors')
    entries = []
    captured = {}
    for index, s in enumerate(members):
        character = s.account.character()
        if character['uid'] != ids[index] or s.identity['id'] != accounts[index]:
            raise ValueError('PvP native member owner')
        def capture(payload, spans):
            captured[s] = (payload, dict(spans))
        body = member(s.account.get_skills(), character, s.account.get_inventory_snapshot()['items'],
                      account_id=accounts[index], peer_port=21100+index, capture=capture)
        # SLOT_STATE.SS_LOADING=4; original confirmations make both ready.
        # First red actor is host. The native +3D alternate-vector selector is0.
        entries.append(bytes((index, 4, int(index == 0), 1, 0, 0)) + i32(index)
                       + u32(1) + body + u32(0) + bytes(4))
    payload = room_info(room_uid, map_id, bootstrap_port) + u32(2) + b''.join(entries)
    payload += u32(0) + u32(0) + bytes(4)
    event = Event(0x201, kind=0x34b, payload=payload)
    if member_captures is not None:
        member_captures.update(captured)
    return event
