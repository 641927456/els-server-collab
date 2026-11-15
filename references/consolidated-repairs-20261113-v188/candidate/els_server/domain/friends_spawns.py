"""Serialized room-wide scripted actors and owner-authenticated player summons.

Reuse the pinned solo decoders/serializers; prepare every actor and mailbox
before committing any session. No persistent effects or hostile kill observers.
"""
import copy
import hashlib
import math
import struct
from collections import deque
from dataclasses import dataclass, field

from els_server.domain.local_session import SessionOrderError
from els_server.domain.summons import sentry_spawn, summon_ack, valid_sentry_death, valid_player_summon_death, player_summon_templates
from els_server.domain.dungeon_lifecycle import death_report, death_ack, empty_reward_death_notice
from els_server.protocol.protocol_codec import encode_event


@dataclass
class Actors:
    epoch: str
    connections: tuple
    generation: tuple
    stage: tuple
    high_key: int
    owners: dict = field(default_factory=dict)
    requests: dict = field(default_factory=dict)
    sequences: dict = field(default_factory=dict)


def _connection(s):
    return s, s.shop_session_id, s.account.uid


def _generation(r, s):
    run = s.dungeon_run
    return ((r.seed, r.identity, run.run_id, run.stage, run.part, run.visits) if run is not None
        else (r.seed, r.identity, r.seed, s.gate_stage, 0, s.gate_stage))


def _stage(generation):
    return generation[3], generation[5]


def _keys(s):
    if s.dungeon_run is not None:
        return s.dungeon_run.reserved_keys | s.summon_keys
    from els_server.domain.dungeon_population import population
    return {n['key'] for n in population(s.gate_stage)['npcs']} | s.summon_keys


def _view(s):
    run = s.dungeon_run
    actors = (tuple((p, run.parts[p]['npcs']) for p in sorted(run.parts)), run.defeated,
        run.dynamic_requests, run.graph['source_sha256']) if run is not None else (s.gate_stage, s.defeated_npcs)
    return actors, s.summon_keys, s.summon_deaths


def _members(dispatcher, r):
    from els_server.domain.equipment_chip_flow import current_lease
    if (tuple(r.party['members']) != r.members or r.party['leader'] is not r.leader
            or len({m.account.uid for m in r.members}) != len(r.members)):
        raise ValueError('Room roster changed')
    for m in r.members:
        if (m.application.world is not dispatcher.world or not current_lease(m)
                or dispatcher.world.party_of.get(m) is not r.owner_party or r.party.get('run') is not r
                or dispatcher.room(m) is not r or m.released or m.coop_error or m.social_overflow
                or not m.application.registry.enabled(m.identity['id'])):
            raise ValueError('Room member unavailable')
    generations = {_generation(r, m) for m in r.members}
    if len(generations) != 1 or any(_view(m) != _view(r.leader) for m in r.members):
        raise ValueError('Room actor state diverged')
    return next(iter(generations))


def _state(r, generation):
    connections = tuple(_connection(m) for m in r.members)
    old = getattr(r, 'shared_actors', None)
    if old is None:
        if any(m.summon_keys for m in r.members):
            raise ValueError('Unowned shared sentries')
        return Actors(r.seed, connections, generation, _stage(generation), max(_keys(r.leader), default=-1))
    if (old.epoch != r.seed or old.connections != connections or old.generation != generation
            or set(old.owners) != r.leader.summon_keys):
        raise ValueError('Room actor generation changed')
    return old


def _allocate(r, state, count, minimum=0):
    first = max(minimum, state.high_key + 1, max(_keys(r.leader), default=-1) + 1)
    if not 1 <= count <= 64 or first + count > 16384:
        raise ValueError('Room actor identity bound')
    return list(range(first, first + count))


def _mailboxes(r, sender, own, broadcast):
    # encode_event is the real transport serializer; the returned ACK and the
    # sender's create notice are validated along with every peer delivery.
    for event in (*own, *broadcast):
        encode_event(event)
    boxes = {}
    for m in r.members:
        if m is sender:
            continue
        box = copy.copy(m.mailbox)
        box.messages = deque(m.mailbox.messages)
        box.moves = dict(m.mailbox.moves)
        for event in broadcast:
            box.append(event)
        boxes[m] = box
    return boxes


def _next_state(state, sender, sequence, digest, key):
    prepared = copy.copy(state)
    prepared.owners = dict(state.owners)
    prepared.requests = dict(state.requests)
    prepared.sequences = dict(state.sequences)
    connection = _connection(sender)
    prepared.requests[connection, sequence] = state.generation, digest
    prepared.sequences[connection] = sequence
    prepared.high_key = key
    return prepared


def spawn(dispatcher, r, s, event, sequence):
    failed = [summon_ack(-1)]
    if (s not in r.members or type(sequence) is not int or not 1 <= sequence < 2**32
            or event.payload_mode != 0):
        return failed
    try:
        generation = _members(dispatcher, r)
        state = _state(r, generation)
        digest = hashlib.sha256(encode_event(event)).digest()
        connection = _connection(s)
        previous = state.requests.get((connection, sequence))
        if previous is not None:
            return [summon_ack(0 if previous[1] == digest else -1)]
        if (r.phase != 'active' or len(state.requests) >= 4096
                or sequence <= state.sequences.get(connection, 0)
                or any(m.phase != 'dungeon_active' or not m.dungeon_substage_synced
                    or m.clear_notified or m.part_end_notified or not m.population_test for m in r.members)):
            return failed

        # A skill-qualified player entity is distinguished by the strict
        # decoder. A guest's general NPC scripts never obtain scene authority.
        minimum = r.leader.dungeon_run.summon_key_floor if r.leader.dungeon_run is not None else 16
        key = _allocate(r, state, 1, minimum=minimum)[0]
        character = s.account.character()
        notice = None
        if s.client_build == 'dx11_260923' and s.role == 'game' and character:
            try:
                notice = sentry_spawn(event.payload, s.account.uid, key, player_summon_templates(character))
            except ValueError:
                pass
        from els_server.domain.dungeon_spawns import occupied_slots, handle as scripted_spawn
        if notice is not None:
            count = struct.unpack_from('>I', notice.payload)[0]
            keys = set(range(key, key + count))
            if occupied_slots(s) + count > 80:
                return failed
            own = [summon_ack(), notice]
            boxes = _mailboxes(r, s, own, [notice])
            prepared = _next_state(state, s, sequence, digest, key + count - 1)
            prepared.owners.update((actor, connection) for actor in keys)
            changes = {m: (m.summon_keys | keys, dict(m.summon_requests)) for m in r.members}
            changes[s][1][sequence] = event.payload
            for m, (keys, requests) in changes.items():
                m.summon_keys = keys
                m.summon_requests = requests
                m.summon_next_key = max(m.summon_next_key, key + count)
        else:
            if s.dungeon_run is None:
                return failed
            # The original adapter mutates only this private prepared view.
            staged = copy.copy(s)
            run = copy.copy(s.dungeon_run)
            run.parts = dict(run.parts)
            run.parts[run.part] = dict(run.current, npcs=[dict(n) for n in run.current['npcs']])
            run.dynamic_requests = dict(run.dynamic_requests)
            run.new_npc_keys = lambda count, other: _allocate(r, state, count, minimum=max(other, default=-1)+1)
            staged.dungeon_run = run
            staged.summon_keys = set(s.summon_keys)
            staged.summon_requests = dict(s.summon_requests)
            own = scripted_spawn(staged, event, sequence, owned_targets_only=s is not r.leader)
            if getattr(staged, '_spawn_diagnostic', (None,))[0] == sequence:
                s._spawn_diagnostic = staged._spawn_diagnostic
            if own is None or [e.kind for e in own] != [0x2cf, 0x2d0] or own[0].payload != bytes(4):
                return failed
            added = run.current['npcs'][len(s.dungeon_run.current['npcs']):]
            player_keys = staged.summon_keys - s.summon_keys
            boxes = _mailboxes(r, s, own, own[1:])
            high_key = max({n['key'] for n in added} | player_keys)
            prepared = _next_state(state, s, sequence, digest, high_key)
            prepared.owners.update((actor, connection) for actor in player_keys)
            changes = {m: (m.dungeon_run.current['npcs'] + [dict(n) for n in added],
                dict(run.dynamic_requests), m.summon_keys | player_keys, dict(m.summon_requests)) for m in r.members}
            if player_keys:changes[s][3][sequence] = event.payload
            for m, (npcs, requests, keys, player_requests) in changes.items():
                m.dungeon_run.current['npcs'] = npcs
                m.dungeon_run.dynamic_requests = requests
                m.summon_keys = keys
                m.summon_requests = player_requests
                if player_keys:m.summon_next_key = max(m.summon_next_key, max(player_keys)+1)
        # All validation, serialization, bounded queue preparation and memory
        # allocation have completed. Only plain reference assignments follow.
        r.shared_actors = prepared
        for m, box in boxes.items():
            m.mailbox = box
        return own
    except (ValueError, OverflowError, struct.error, SessionOrderError):
        return failed


def retire(dispatcher, r, s, event):
    state = getattr(r, 'shared_actors', None)
    if state is None:
        return None
    try:
        data = death_report(event.payload)
    except ValueError:
        return []
    key = data['index']
    if key not in state.owners:
        # The existing solo flow also accepts this native expiry shape for
        # declared dynamic scene actors. A shared actor must retire in every
        # view. The native readiness map can name the complete room roster.
        if data['flag'] == 255 and r.leader.dungeon_run is not None:
            npc = next((n for part in r.leader.dungeon_run.parts.values() for n in part['npcs']
                if n['key'] == key and n.get('dynamic')), None)
            if npc is not None:
                return _scene_expiry(dispatcher, r, s, event, data, npc)
        return None
    try:
        generation = _members(dispatcher, r)
        state = _state(r, generation)
        loading_expiry = (r.phase == 'substage' and data['flag'] == 255
            and all(m.phase == 'dungeon_active' and m.gate_stage_loading for m in r.members))
        if (state.owners[key] != _connection(s) or event.performers != (0,)
                or not loading_expiry and (r.phase not in ('active', 'part_end', 'clear')
                    or any(m.phase != 'dungeon_active' or not m.dungeon_substage_synced for m in r.members))
                or not valid_player_summon_death(data, s.account.uid,
                    _keys(s) | {m.account.uid for m in r.members},
                    participants=tuple(m.account.uid for m in r.members))):
            return []
        previous = s.summon_deaths.get(key)
        if previous is not None:
            return [death_ack()] if previous == event.payload else []
        own = [death_ack(), empty_reward_death_notice(key, data['killer'])]
        boxes = _mailboxes(r, s, own, own[1:])
        deaths = {m: {**m.summon_deaths, key: bytes(event.payload)} for m in r.members}
        for m, records in deaths.items():
            m.summon_deaths = records
        for m, box in boxes.items():
            m.mailbox = box
        return own
    except (ValueError, OverflowError, struct.error, SessionOrderError):
        return []


def _scene_expiry(dispatcher, r, s, event, data, npc):
    """Preserve the original master-only dynamic expiry policy in every view."""
    from els_server.domain.scene_actor_retirements import dynamic_retirement_shape
    try:
        _state(r, _members(dispatcher, r))
        hp = struct.unpack('>f', struct.pack('>I', data['hp_bits']))[0]
        owners = tuple(m.account.uid for m in r.members)
        # Keep the already supported master-only form, and bind a full native
        # readiness map to this exact room rather than to a single player.
        readiness_owners = (s.account.uid,) if set(data['readiness']) == {s.account.uid} else owners
        if (s is not r.leader or r.phase not in ('active', 'part_end', 'clear') or event.performers != (0,)
                or event.uid != 2**64-1 or event.target_uid != 2**64-1 or event.payload_mode != 0
                or not dynamic_retirement_shape(s.dungeon_run, npc, data, readiness_owners,
                    last_hit_participants=owners)
                or not math.isfinite(hp)
                or any(m.phase != 'dungeon_active' or not m.dungeon_substage_synced for m in r.members)):
            return []
        key = npc['key']
        previous = s.dungeon_run.defeated.get(key)
        if previous is not None:
            return [death_ack()] if previous == event.payload else []
        source_part = next(part for part, value in s.dungeon_run.parts.items()
            if any(n is npc for n in value['npcs']))
        late = source_part != s.dungeon_run.part
        if r.phase not in ('active', 'part_end') or any(m.clear_notified for m in r.members):
            return []
        from els_server.domain.dungeon_flow import periodic, failed
        prepared = {}
        deliveries = {}
        boxes = {}
        for m in r.members:
            shadow = copy.copy(m)
            run = copy.copy(m.dungeon_run)
            run.parts = dict(run.parts)
            source = run.parts[source_part]
            run.parts[source_part] = dict(source, npcs=[dict(n) for n in source['npcs']])
            next(n for n in run.parts[source_part]['npcs'] if n['key'] == key)['active'] = False
            run.defeated = {**run.defeated, key: bytes(event.payload)}
            shadow.dungeon_run = run
            shadow.defeated_npcs = run.defeated
            shadow.dungeon_clock = copy.copy(m.dungeon_clock)
            # These are exactly the original expired-actor failure/periodic
            # branches. No loot hook runs for an expired dynamic actor.
            messages = [empty_reward_death_notice(key, data['killer'])]
            if not late and r.phase == 'active':
                messages += failed(shadow) if run.identity == 38300 and npc['template'] == 1368 else periodic(shadow)
            if m is s:
                messages.insert(0, death_ack())
            for message in messages:
                encode_event(message)
            deliveries[m] = messages
            prepared[m] = shadow
            if m is not s:
                box = copy.copy(m.mailbox)
                box.messages = deque(m.mailbox.messages)
                box.moves = dict(m.mailbox.moves)
                for message in messages:
                    box.append(message)
                boxes[m] = box
        for m, shadow in prepared.items():
            run = m.dungeon_run
            run.parts = shadow.dungeon_run.parts
            run.defeated = shadow.dungeon_run.defeated
            run.next = shadow.dungeon_run.next
            run.ready_at = shadow.dungeon_run.ready_at
            m.defeated_npcs = run.defeated
            m.dungeon_clock = shadow.dungeon_clock
            m.part_end_notified = shadow.part_end_notified
            m.clear_notified = shadow.clear_notified
            m.reward_receipt = shadow.reward_receipt
            if hasattr(shadow, 'dungeon_failed'):
                m.dungeon_failed = shadow.dungeon_failed
        for m, box in boxes.items():
            m.mailbox = box
        if not late and r.phase == 'active':
            dispatcher.part_wait(r)
        return deliveries[s]
    except (ValueError, OverflowError, struct.error, SessionOrderError):
        return []


def retry_death(dispatcher, r, s, event):
    """Acknowledge an accepted actor in the still-loaded stage; never apply AD."""
    if (s is not r.leader or r.phase not in ('part_end', 'clear')
            or event.event_id != 0x202 or event.kind != 0xad
            or event.performers != (0,) or event.payload_mode != 0
            or getattr(r, 'shared_actors', None) is None or s.dungeon_run is None):
        return []
    try:
        _state(r, _members(dispatcher, r))
        if (any(m.phase != 'dungeon_active' or not m.dungeon_substage_synced for m in r.members)
                or r.phase == 'part_end' and not all(m.part_end_notified for m in r.members)
                or r.phase == 'clear' and not all(m.clear_notified for m in r.members)):
            return []
        data = death_report(event.payload)
        key = data['index']
        # B2 replaces parts and clears defeated; a curtain keeps both intact.
        npc = next((n for part in s.dungeon_run.parts.values() for n in part['npcs']
            if n['key'] == key and n.get('dynamic')), None)
        if npc is None or s.dungeon_run.defeated.get(key) != event.payload:
            return []
        ack = death_ack()
        encode_event(ack)
        return [ack]
    except (ValueError, OverflowError, struct.error, SessionOrderError):
        return []


def _static_origin(r):
    return (r, _connection(r.leader), r.seed, r.identity, tuple(
        (_connection(m), m.dungeon_run, getattr(m.dungeon_run, 'run_id', None)) for m in r.members))


def capture_static_origin(r):
    """Record existing authenticated objects and gate after ordinary start."""
    if r.identity == 30000 and all(m.dungeon_run is None for m in r.members):
        return
    origin = _static_origin(r)
    generation = _generation(r, r.leader)
    r.static_actor_origin = origin
    r.static_actor_generation = generation


def _checked_static_generation(dispatcher, r):
    if getattr(r, 'static_actor_origin', None) != _static_origin(r):
        raise ValueError('Static actor room origin changed')
    generation = _members(dispatcher, r)
    if getattr(r, 'static_actor_generation', None) != generation:
        raise ValueError('Static actor gate changed')
    if getattr(r, 'shared_actors', None) is not None:
        _state(r, generation)
    participants = frozenset(m.account.uid for m in r.members)
    if any(m.role != 'game' or m.phase != 'dungeon_active' or not m.dungeon_substage_synced
            or m.dungeon_run is None or m.dungeon_run.identity != r.identity
            or m.dungeon_run.run_id != r.seed or m.dungeon_participants != participants for m in r.members):
        raise ValueError('Static actor member unavailable')
    return generation


def prepare_static_transition(dispatcher, r, sender):
    """Prepare before r.ended.add and any original per-member advancement."""
    if not hasattr(r, 'static_actor_origin'):
        return None
    generation = _checked_static_generation(dispatcher, r)
    if (sender not in r.members or r.phase != 'part_end'
            or not all(m.part_end_notified for m in r.members)):
        raise ValueError('Static actor barrier unavailable')
    target = r.leader.dungeon_run.next
    if not isinstance(target, dict) or type(target.get('kind')) is not int:
        raise ValueError('Static actor target missing')
    if target['kind'] != 4 and (type(target.get('stage')) is not int or type(target.get('part')) is not int):
        raise ValueError('Static actor target type')
    entries = tuple((m, m.dungeon_run) for m in r.members)
    for m, run in entries:
        now = run.clock()
        if (run.next != target or type(run.ready_at) not in (int, float) or not math.isfinite(run.ready_at)
                or type(now) not in (int, float) or not math.isfinite(now) or now < run.ready_at):
            raise ValueError('Static actor targets diverged or are not ready')
        if target['kind'] != 4 and (str(target['stage']) not in run.graph['stages']
                or str(target['part']) not in run.graph['stages'][str(target['stage'])]['parts']):
            raise ValueError('Static actor target absent from source')
    # These are exactly DungeonRun.advance's already-selected target branches;
    # no poll_ready/RNG, target selection, actor construction or mutation runs.
    stage, part, visits = generation[3:]
    if target['kind'] != 4:
        part = target['part']
        if target['kind'] == 0:
            if target['stage'] != stage:
                raise ValueError('Static sub-part crosses stage')
        else:
            stage = target['stage']
            visits += 1
    if type(stage) is not int or type(part) is not int or type(visits) is not int:
        raise ValueError('Static actor target type')
    expected = (*generation[:3], stage, part, visits)
    return expected, entries, stage, part, visits


def commit_static_generation(r, prepared):
    """No validation exceptions after original advance; mismatch disables ACKs."""
    if prepared is None:
        return
    expected, entries, stage, part, visits = prepared
    for member, run in entries:
        if (member.dungeon_run is not run or run.run_id != expected[2]
                or run.stage != stage or run.part != part or run.visits != visits):
            r.static_actor_generation = None
            return
    r.static_actor_generation = expected


def retry_static_death(dispatcher, r, s, event):
    """Read an accepted loaded-stage static AD; never create Actors or apply AD."""
    if (s is not r.leader or r.phase not in ('part_end', 'clear')
            or event.event_id != 0x202 or event.kind != 0xad
            or event.performers != (0,) or event.payload_mode != 0 or s.dungeon_run is None):
        return []
    try:
        _checked_static_generation(dispatcher, r)
        if (r.phase == 'part_end' and not all(m.part_end_notified for m in r.members)
                or r.phase == 'clear' and not all(m.clear_notified for m in r.members)):
            return []
        data = death_report(event.payload)
        key = data['index']
        npc = next((n for part in s.dungeon_run.parts.values() for n in part['npcs']
            if n['key'] == key and not n.get('dynamic')), None)
        if npc is None or s.dungeon_run.defeated.get(key) != event.payload:
            return []
        ack = death_ack()
        encode_event(ack)
        return [ack]
    except (ValueError, OverflowError, struct.error, SessionOrderError):
        return []


def advance(r):
    """Called only after the existing all-member part transition completes."""
    state = getattr(r, 'shared_actors', None)
    if state is None:
        return
    generations = {_generation(r, m) for m in r.members}
    if len(generations) != 1:
        raise SessionOrderError('Shared actor transition diverged')
    generation = next(iter(generations))
    # The native dungeon keeps reason3 actors and their owner timers. Keep the
    # same owner/expiry/request records for this room epoch, without a spawn.
    state.generation = generation
    state.stage = _stage(generation)


def retry_late_portal(dispatcher, r, s, event):
    """Acknowledge one genuine completed stage endpoint without opening a gate."""
    try:
        if (r.phase != 'substage' or type(r.identity) is not int
                or event.event_id != 0x202 or event.kind != 0xb8
                or event.performers not in ((),(0,)) or event.payload_mode != 0
                or event.uid != 2**64-1 or event.target_uid != 2**64-1
                or type(event.payload) is not bytes or len(event.payload) != 1
                or s not in r.members or not 2 <= len(r.members) <= 6):
            return []
        if getattr(r, 'static_actor_origin', None) != _static_origin(r):
            return []
        generation = _members(dispatcher, r)
        if getattr(r, 'static_actor_generation', None) != generation or r.party['run'] is not r:
            return []
        if getattr(r, 'shared_actors', None) is not None:
            actors = _state(r, generation)
            if actors.stage != _stage(generation):
                return []
        participants = frozenset(m.account.uid for m in r.members)
        if type(r.previous_part) is not int:
            return []
        expected_parts = frozenset((struct.pack('>b', r.previous_part), struct.pack('>b', r.leader.dungeon_run.part)))
        for member in r.members:
            account = member.account
            app = member.application
            account_id = member.identity['id']
            run = member.dungeon_run
            root = app.accounts.get(account_id)
            if (type(account_id) is not int or type(account.uid) is not int
                    or app.playing.get(account_id) is not member
                    or account.account_id != account_id or root is None or account.root is not root
                    or root.character_accounts.get(account.uid) is not account
                    or account.store.uid != account.uid or app.world is not dispatcher.world
                    or dispatcher.world.party_of.get(member) is not r.owner_party
                    or member.role != 'game' or member.client_build != 'dx11_260923'
                    or run is None or run.identity != r.identity or run.run_id != r.seed
                    or any(type(v) is not int for v in (run.stage, run.part, run.visits))
                    or type(member.dungeon_participants) is not frozenset
                    or member.dungeon_participants != participants
                    or member.phase != 'dungeon_active' or member.dungeon_substage_synced is not False
                    or member.gate_stage_loading is not True or member.clear_notified is not False
                    or member.part_end_notified is not False or member.dungeon_return_pending
                    or getattr(member, 'dungeon_failed', False) or member.dungeon_end_payload is not None
                    or member.reward_receipt is not None):
                return []
            cache = run.completed_transition
            if (type(cache) is not dict or set(cache) != {'target', 'parts'}
                    or type(cache['target']) is not tuple or len(cache['target']) != 3
                    or any(type(v) is not int for v in cache['target'])
                    or cache['target'] != (run.stage, run.part, run.visits)
                    or type(cache['parts']) is not tuple or not 1 <= len(cache['parts']) <= 2
                    or any(type(p) is not bytes or len(p) != 1 for p in cache['parts'])
                    or len(frozenset(cache['parts'])) != len(cache['parts'])
                    or frozenset(cache['parts']) != expected_parts or event.payload not in expected_parts):
                return []
        from els_server.protocol.protocol_codec import Event
        ack = Event(0x201, kind=0xb9, payload=bytes(4))
        encode_event(ack)
        return [ack]
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError, struct.error, SessionOrderError):
        return []
