"""Player entities in native field/PvP rooms, without enemy or reward effects.

Dungeon rooms retain friends_spawns' existing generation and scene barriers.
These rooms have one native scene; actor ownership belongs to that room and
connection, not to a session's previous dungeon summon set.
"""
import hashlib
import struct
from dataclasses import dataclass, field

from els_server.domain.summons import sentry_spawn, summon_ack, valid_player_summon_death, player_summon_templates
from els_server.domain.dungeon_lifecycle import death_report, death_ack, empty_reward_death_notice
from els_server.domain.party_commands import _prepared_boxes
from els_server.domain.local_session import SessionOrderError


@dataclass
class Actors:
    generation: tuple
    next_key: int
    owners: dict = field(default_factory=dict)
    requests: dict = field(default_factory=dict)
    deaths: dict = field(default_factory=dict)


def _connection(s):
    return s, s.shop_session_id, s.account.uid


def handle(manager, room, s, event, sequence, *, pvp=False):
    if event.kind not in (0x2ce, 0xad):
        return None
    state = getattr(room, 'player_summons', None)
    data = None
    if event.kind == 0xad:
        try:
            data = death_report(event.payload)
        except ValueError:
            return []
        if state is None or data['index'] not in state.owners:
            return None
    failed = [summon_ack(-1)] if data is None else []
    try:
        from els_server.domain.equipment_chip_flow import current_lease
        if (s not in room.members or event.event_id != 0x202 or event.payload_mode != 0
                or event.performers not in ((), (0,))
                or event.uid != event.target_uid or event.uid != 2**64-1
                or any(manager.room(m) is not room or getattr(m, 'released', False)
                       or getattr(m, 'coop_error', None) or getattr(m, 'social_overflow', False)
                       or not current_lease(m)
                       or m.role != 'game' or m.client_build != 'dx11_260923' for m in room.members)):
            return failed
        generation = room.seed, tuple(_connection(m) for m in room.members)
        if state is not None and state.generation != generation:
            return failed
        if data is not None:
            key = data['index']
            if (state.owners[key] != _connection(s) or event.performers != (0,)
                    or not valid_player_summon_death(data, s.account.uid,
                        set(state.owners) | {m.account.uid for m in room.members} |
                        ({n['key'] for n in room.entries} if not pvp else set()))):
                return []
            previous = state.deaths.get(key)
            if previous is not None:
                return [death_ack()] if previous == event.payload else []
            own = [death_ack(), empty_reward_death_notice(key, data['killer'])]
            boxes = _prepared_boxes([(m, own[1:]) for m in room.members if m is not s], own)
            deaths = {**state.deaths, key: bytes(event.payload)}
            state.deaths = deaths
            for m, box in boxes.items():
                m.mailbox = box
            return own

        if (room.phase != 'active' or s not in room.loaded
                or s.phase != ('pvp_active' if pvp else 'field_active')
                or type(sequence) is not int or not 1 <= sequence < 2**32):
            return failed
        entries = () if pvp else room.entries
        if state is None:
            state = Actors(generation, max(16, max((n['key'] for n in entries), default=-1)+1))
        identity = _connection(s), sequence
        digest = hashlib.sha256(event.payload).digest()
        previous = state.requests.get(identity)
        if previous is not None:
            return [summon_ack(0 if previous == digest else -1)]
        occupied = sum(n['key'] not in room.defeated for n in entries)
        occupied += len(state.owners) - len(state.deaths)
        if occupied >= 80 or len(state.requests) >= 4096:
            return failed
        templates = player_summon_templates(s.account.character(), 'pvp' if pvp else 'pve')
        key = state.next_key
        notice = sentry_spawn(event.payload, s.account.uid, key, templates)
        count = struct.unpack_from('>I', notice.payload)[0]
        if occupied + count > 80:
            return failed
        own = [summon_ack(), notice]
        boxes = _prepared_boxes([(m, [notice]) for m in room.members if m is not s], own)
        owners = {**state.owners, **dict.fromkeys(range(key, key + count), _connection(s))}
        requests = {**state.requests, identity: digest}
        state.owners = owners
        state.requests = requests
        state.next_key = key+count
        room.player_summons = state
        for m, box in boxes.items():
            m.mailbox = box
        return own
    except (ValueError, OverflowError, struct.error, SessionOrderError):
        return failed
