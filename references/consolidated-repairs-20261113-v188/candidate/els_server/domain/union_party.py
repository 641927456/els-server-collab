"""Native type-6 striker party membership and the AA1 group editor."""
import struct
import time
from dataclasses import replace

from els_server.domain.local_session import SessionOrderError
from els_server.domain.party_commands import _forget_invitations, _prepared_boxes
from els_server.protocol import social_messages as wire, union_messages as union
from els_server.protocol.protocol_codec import Event


def waiting(world, party):
    return not any(party.get(key) for key in (
        'challenge', 'challenge_pending', 'challenge_cancel_pending'
    )) and outside_dungeons(world, party)


def outside_dungeons(world, party):
    return not (party['run'] or party.get('union_runs')) and all(
        member.phase == 'town_ready' and member in world.members
        and world.party_of.get(member) is party and world.dungeons.room(member) is None
        and owned(member)
        for member in party['members']
    )


def owned(session):
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    return (current_lease(session) and session.application.config.friends_coop_enabled
            and session.application.registry.enabled(session.account.account_id))


def bind_attempt(party):
    party.pop('union_signals', None)
    party['union_attempt_leader'] = party['leader'].account.uid
    party['union_attempt_roster'] = {
        member.account.uid: (member.account.account_id, party['union_groups'][member.account.uid])
        for member in party['members']
    }


def active_roster(party):
    state = party.get('challenge')
    if state and not state['complete'] and state['deadline'] > time.time():
        return party.get('union_attempt_roster')
    return None


def can_rejoin(world, party, session):
    roster = active_roster(party)
    saved = roster.get(session.account.uid) if roster else None
    return (saved is not None and saved[0] == session.account.account_id
            and session.phase == 'town_ready' and world.dungeons.room(session) is None
            and all(m.account.uid != session.account.uid for m in party['members'])
            and outside_dungeons(world, party))


def invite_selection(world, session, target, party, request):
    if (request['kind'] != 6 or not owned(session) or not owned(target)
        or request['fields'][0] or request['fields'][2]):
        return None
    if party is not None:
        if not party.get('union_party'):
            return None
        if can_rejoin(world, party, target):
            return party['dungeon']
        if not waiting(world, party):
            return None
        try:
            if party.get('recruitment'):
                from els_server.domain.party_recruitment import source
                source({**party, 'members': [*party['members'], target]})
        except ValueError:
            return None
        return party['dungeon']
    # The invitation carries a presentation map. Actual entry needs a phase.
    from els_server.game_data import client_data
    try:
        client_data().dungeon(request['dungeon'])
    except ValueError:
        return None
    return request['dungeon']


def accept(world, session, invitation, *, display_power=None):
    from els_server.domain.normal_party import publish_join
    from els_server.domain.raid_party import capacity

    inviter = invitation['inviter']
    party = invitation['party']
    dungeon = invitation['union_selection']
    rejoin = invitation.get('rejoin_attempt')
    if (not owned(inviter) or not owned(session)
        or party is not None and (party['leader'] is not inviter
                                  or party['dungeon'] != dungeon or len(party['members']) >= capacity(party))):
        return [wire.party_join_failed()]
    if rejoin is not None:
        if not can_rejoin(world, party, session) or party['challenge']['attempt'] != rejoin:
            return [wire.party_join_failed()]
        roster = party['union_attempt_roster']
        live = {m.account.uid: m for m in (*party['members'], session)}
        after = {**party, 'members': [live[uid] for uid in roster if uid in live], 'ready': set(),
                 'leader': live.get(party['union_attempt_leader'], inviter),
                 'union_groups': {uid: roster[uid][1] for uid in live}}
        reconcile(after)
        return publish_join(world, session, invitation, after, display_power=display_power)
    if party is not None and not waiting(world, party):
        return [wire.party_join_failed()]
    after = dict(party) if party else dict(
        id=world.next_party, leader=inviter, members=[inviter], ready=set(),
        dungeon=dungeon, difficulty=0, mode=0, run=None, union_party=True,
        union_groups={inviter.account.uid: (0, True)},
    )
    after.update(members=[*after['members'], session], ready=set(), union_groups=joined_groups(after, session))
    try:
        if after.get('recruitment'):
            from els_server.domain.party_recruitment import source
            source(after)
    except ValueError:
        return [wire.party_join_failed()]
    return publish_join(world, session, invitation, after, display_power=display_power)


def joined_groups(party, session):
    groups = dict(party['union_groups'])
    for group in (0, 1):
        count = sum(number == group for number, _ in groups.values())
        if count < 4:
            groups[session.account.uid] = (group, count == 0)
            return groups
    raise ValueError('Striker party full')


def edit(world, session, event):
    party = world.party_of.get(session)
    denied = [union.ack(-1)]
    if (event.payload_mode or party is None or not party.get('union_party')
        or party['leader'] is not session or not waiting(world, party)):
        return denied
    try:
        groups = union.assignments(event.payload)
    except ValueError:
        return denied
    members = tuple(party['members'])
    if set(groups) != {member.account.uid for member in members}:
        return denied
    changed = groups != party['union_groups']
    after = {**party, 'union_groups': groups, 'ready': set() if changed else party['ready']}
    response = [union.ack()]
    notices = [union.snapshot(after)]
    if changed:
        notices.extend(wire.party_ready_notice(member.account.uid, False) for member in members)
    try:
        boxes = _prepared_boxes([(member, notices) for member in members], response)
    except SessionOrderError:
        return denied
    if changed:
        party['union_groups'] = groups
        party['ready'].clear()
        party.pop('admission', None)
        _forget_invitations(world, party, session)
    for member, box in boxes.items():
        member.mailbox = box
    return response


def reconcile(party):
    groups = {member.account.uid: party['union_groups'][member.account.uid] for member in party['members']}
    for group in (0, 1):
        selected = [uid for uid, (number, _) in groups.items() if number == group]
        if selected and not any(groups[uid][1] for uid in selected):
            groups[selected[0]] = (group, True)
    party['union_groups'] = groups
    party['ready'].clear()
    party.pop('admission', None)


def other_group(room):
    group = room.party.get('striker_group')
    if group is None:
        return ()
    party = room.owner_party
    return tuple(m for m in party['members'] if party['union_groups'][m.account.uid][0] != group)


def battle_signal(dispatcher, room, session, event):
    denied = [union.battle_ack(-1)]
    if (room is None or room.owner_party is room.party or room.leader is not session
        or room.phase not in ('active', 'part_end') or event.payload_mode
        or event.performers not in ((), (0,)) or len(event.payload) != 16
        or event.uid != 2**64-1 or event.target_uid != 2**64-1
        or not dispatcher._current_transport_roster(session.application,room)):
        return denied
    party = room.owner_party
    state = party['challenge']
    if state['complete'] or state['deadline'] <= time.time():
        return denied
    destination, stage, slot, _ = struct.unpack('>iiIi',event.payload)
    if stage < -1 or slot >= 20:  # Native dungeon object initializes 20 dwords at +BAC.
        return denied
    # Opposite-map calls in the challenge NPC scripts, plus the current map.
    linked = ((34850,34860),(34890,34900),(34930,34940),(34960,34970))
    if destination != room.identity and not any({room.identity,destination} == set(pair) for pair in linked):
        return denied
    if stage >= 0:
        from els_server.domain.dungeon_routes import route_catalog
        if str(stage) not in route_catalog().graph(destination,internal=True)['stages']:
            return denied
    notice = union.battle_signal(event.payload)
    target = next((target for target in party['union_runs'].values()
                   if target.identity == destination), None)
    response = [union.battle_ack()]
    if target is not None and (target.party['challenge'] is not state or target.phase == 'clear'
                               or 0 <= stage < target.leader.gate_stage):
        return denied
    if (target is None or target.phase not in ('active','part_end')
        or stage not in (-1,target.leader.gate_stage)
        or not dispatcher._current_transport_roster(session.application,target)):
        # AA6 updates a slot. Keep the latest value until the target's native
        # scene can consume it, including when the other group enters later.
        signals=party.setdefault('union_signals', {})
        signals.pop((destination,stage,slot),None)
        signals[destination,stage,slot] = notice
        return response
    try:
        boxes = _prepared_boxes([(m,[notice]) for m in target.members],response)
    except SessionOrderError:
        return denied
    for member,box in boxes.items():
        member.mailbox = box
    party.get('union_signals', {}).pop((destination,stage,slot),None)
    return response


def flush_battle_signals(dispatcher, room):
    if room.party.get('striker_group') is None:
        return
    signals = room.owner_party.get('union_signals')
    if (not signals or room.phase != 'active'
        or not dispatcher._current_transport_roster(room.leader.application,room)):
        return
    current = room.leader.gate_stage
    notices = []
    for key, notice in tuple(signals.items()):
        destination, stage, _ = key
        if destination != room.identity or stage > current:
            continue
        del signals[key]
        if stage in (-1,current):
            notices.append(notice)
    for member in room.members:
        dispatcher.send(member,notices)


def close_inactive_attempt(party):
    state = party.get('challenge')
    if state is None or party.get('union_runs') or not (state['complete'] or time.time() >= state['deadline']):
        return False
    party.pop('challenge')
    party.pop('challenge_cancel_pending', None)
    party.pop('union_selections', None)
    party.pop('union_signals', None)
    party.pop('union_attempt_roster', None)
    party.pop('union_attempt_leader', None)
    party['ready'].clear()
    return True


def node_roster(party, actor, identity):
    from els_server.game_data import client_data
    from els_server.storage.challenge_state import eligible

    state = party.get('challenge')
    node = eligible(state, identity, int(time.time()))
    original = active_roster(party)
    if (node is None or party.get('challenge_cancel_pending') or original is None
        or len(original) != len(party['members'])):
        return None
    group, leader = party['union_groups'][actor.account.uid]
    if not leader:
        return None
    definition = client_data().dungeon(identity)
    merged = 53 in definition['DUNGEON_CHECK_CONDITION'].values()
    key = None if merged else group
    rooms = party.get('union_runs', {})
    if (merged and rooms) or None in rooms or key in rooms:
        return None
    # Two distinct one-clear nodes may run concurrently, each in its own room.
    if any(room.identity == identity for room in rooms.values()):
        return None
    members = tuple(member for member in party['members']
                    if merged or party['union_groups'][member.account.uid][0] == group)
    if not definition['m_MinPlayerCount'] <= len(members) <= definition['m_MaxPlayerCount']:
        return None
    return key, members


def select(world, actor, event):
    ack = lambda code: [Event(0x201, kind=0x146, payload=struct.pack('>i', 222 if code == -1 else code))]
    if event.payload_mode or len(event.payload) != 6 or actor not in world.members or not owned(actor):
        return ack(2)
    identity, difficulty, mode = struct.unpack('>ibb', event.payload)
    party = world.party_of[actor]
    roster = node_roster(party, actor, identity)
    if difficulty or mode or roster is None:
        return ack(2)
    key, members = roster
    if any(member not in world.members or not owned(member) for member in members):
        return ack(2)
    group = party['union_groups'][actor.account.uid][0]
    before = party.get('union_selections', {})
    selection = (key, identity)
    if key is None:
        choices = dict.fromkeys((0, 1), selection)
    else:
        choices = {number: selected for number, selected in before.items() if selected[0] is not None}
        choices[group] = selection
    changed = choices != before
    clearing_merged = key is not None and any(selected[0] is None for selected in before.values())
    recipients = party['members'] if clearing_merged else members
    selected_notice = Event(0x201, kind=0x147, payload=event.payload)
    waiting_notice = Event(0x201, kind=0x147, payload=struct.pack('>ibb', party['dungeon'], 0, 0))
    ready_notices = [wire.party_ready_notice(member.account.uid, False) for member in recipients] if changed else []
    response = ack(0)
    try:
        boxes = _prepared_boxes([
            (member, [selected_notice if member in members else waiting_notice, *ready_notices])
            for member in recipients
        ], response)
    except SessionOrderError:
        return ack(2)
    if changed:
        party['union_selections'] = choices
        party['ready'].difference_update(recipients)
    for member, box in boxes.items():
        member.mailbox = box
    return response


def enter(dispatcher, party, actor, event, *, request_sequence=None):
    from els_server.domain.raid_native_power import request as native_power_request
    from els_server.protocol.dungeon_errors import ENTRY_REQUIREMENTS_NOT_MET

    def reply(result):
        if event.kind == 0x7d4:
            return [Event(0x201, kind=0x7d5, payload=struct.pack('>ii', result, 1))]
        from els_server.protocol.dungeon_messages import entry_ack
        return [entry_ack(0x383,result)]

    denied = ENTRY_REQUIREMENTS_NOT_MET
    if not owned(actor) or event.payload_mode:
        return reply(denied)
    try:
        payload = native_power_request(actor, event.payload, fresh=event.kind == 0x7d4)
    except ValueError:
        return reply(denied)
    if event.kind == 0x7d4:
        preflight = struct.unpack('>ii', payload) if len(payload) == 8 else None
        actor._admission_diagnostic = (request_sequence, preflight[1] if preflight else None)
    group = party['union_groups'][actor.account.uid][0]
    selection = party.get('union_selections', {}).get(group)
    if selection is None:
        return reply(denied)
    key, identity = selection
    roster = node_roster(party, actor, identity)
    if roster is None or roster[0] != key:
        return reply(denied)
    members = roster[1]
    if any(not owned(member) or dispatcher.world.party_of.get(member) is not party
           or dispatcher.room(member) is not None for member in members):
        return reply(denied)
    run = dict(id=party['id'], leader=actor, members=members, ready=party['ready'].intersection(members),
               dungeon=identity, difficulty=0, mode=0, run=None, challenge=party['challenge'],
               striker_parent=party, striker_group=key)
    if event.kind == 0x7d4:
        if preflight != (1, identity):
            return reply(denied)
        return reply(dispatcher.admission_result(run, actor, identity))
    if not 23 <= len(payload) <= 86 or not any(
        struct.unpack_from('>I', payload, offset)[0] == len(payload) - 22 for offset in range(19)
    ):
        return reply(denied)
    result = dispatcher.admission_result(run, actor, identity)
    if result:
        return reply(result)
    return reply(0 if dispatcher.start(run, actor, identity, replace(event, payload=payload)) else denied)
