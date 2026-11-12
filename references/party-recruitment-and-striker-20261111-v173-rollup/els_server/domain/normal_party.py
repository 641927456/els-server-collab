"""Server-owned ordinary room state; original13B and147 own client rendering."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol import social_messages as wire


def ordinary(party):
    return not any(party.get(k) for k in ('raid_party','solo_challenge','challenge','challenge_pending','racing','union_party'))


def roster_events(party,reset=False):
    events=([wire.party_removed()] if reset else [])+[wire.party_snapshot(party)]
    # Original2D59FA0 installs13B then overwrites its map with local UI state.
    # Original2D618E0's147 reapplies the canonical server selection afterwards.
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.raid_party import raid_definition
    if ((ordinary(party) or party.get('raid_party')) and route_catalog().supports(party['dungeon'])
        and bool(party.get('raid_party'))==(raid_definition(party['dungeon']) is not None)
        and party.get('difficulty',0)==0 and party.get('mode',0)==0):
        events.append(Event(0x201,kind=0x147,payload=struct.pack('>ibb',party['dungeon'],party.get('difficulty',0),party.get('mode',0))))
    return events


def invite_selection(world,session,target,party,request):
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.raid_party import waiting_size,raid_definition
    from els_server.domain.region_quests import account_dungeon_allowed
    # 2D5CFA0/2BDD530: fields0=difficulty(+14), fields2=mode(+40).
    # The other room settings remain outside this narrow ordinary selection.
    if request['fields'][0]!=0 or request['fields'][2]!=0:return None
    if party is not None and not ordinary(party):return None
    selected=(party['dungeon'],party.get('difficulty',0),party.get('mode',0)) if party else (route_catalog().entry_identity(request['dungeon']),0,0)
    identity,difficulty,mode=selected
    if difficulty or mode or not route_catalog().supports(identity) or raid_definition(identity) is not None:return None
    members=[*(party['members'] if party else [session]),target]
    proposed=dict(members=members,dungeon=identity)
    if party is not None and party.get('recruitment'):proposed['recruitment']=party['recruitment']
    if proposed.get('recruitment'):
        from els_server.domain.party_recruitment import source
        try:source(proposed)
        except ValueError:return None
    elif not waiting_size(proposed,identity) or any(not account_dungeon_allowed(m.account,identity) for m in members):return None
    return selected


def accept(world,session,invite,*,display_power=None):
    from els_server.domain.raid_party import waiting_size
    from els_server.domain.region_quests import account_dungeon_allowed
    inviter=invite['inviter'];party=invite['party'];selection=invite.get('ordinary_selection')
    denied=lambda:[wire.party_join_failed()]
    if selection is None or party is not None and (not ordinary(party) or party['run'] is not None or party['leader'] is not inviter):return denied()
    selected=(party['dungeon'],party.get('difficulty',0),party.get('mode',0)) if party else selection
    if selected!=selection:return denied()
    old_members=tuple(party['members']) if party else (inviter,)
    members=[*old_members,session]
    if any(m.released or m.phase!='town_ready' or m not in world.members for m in members):return denied()
    if party is not None and any(world.party_of.get(m) is not party for m in old_members):return denied()
    if session in world.party_of:return denied()
    after={**party,'members':members,'ready':set()} if party else dict(id=world.next_party,leader=inviter,members=members,ready=set(),dungeon=selection[0],difficulty=selection[1],mode=selection[2],run=None,raid_party=False)
    if after.get('recruitment'):
        from els_server.domain.party_recruitment import source
        try:source(after)
        except ValueError:return denied()
    elif not waiting_size(after,selection[0]) or any(not account_dungeon_allowed(m.account,selection[0]) for m in members):return denied()
    return publish_join(world,session,invite,after,display_power=display_power)


def publish_join(world,session,invite,after,*,display_power=None):
    from els_server.domain.party_commands import _prepared_boxes
    from els_server.domain.party_recruitment import removal_plan,prepare,actor
    from els_server.domain.raid_party import capacity
    from els_server.domain.raid_native_power import remember_party_display
    from els_server.protocol.party_recruitment_messages import info_notice
    party=invite['party'];members=after['members'];inviter=invite['inviter']
    response=[]
    full_recruitment=party if after.get('recruitment') and len(members)>=capacity(after) else None
    try:
        remember_party_display(session,display_power)
        notices=roster_events(after)
        if invite.get('rejoin_attempt'):
            from els_server.protocol.challenge_messages import phase_notice
            state=after['challenge']
            notices.append(phase_notice(state['challenge'],state['phase'],state['progress'],state['deadline'],
                actor=after['union_attempt_leader'],members=tuple(after['union_attempt_roster'])))
        if after.get('recruitment'):notices.append(info_notice(after))
        pending,deliveries=removal_plan(world,applicant=session,party=full_recruitment)
        for member in members:
            reset=[wire.party_removed()] if party is not None and member is not session else []
            deliveries.append((member,[*reset,*notices]))
        if after.get('recruitment') or len(deliveries)>len(members):
            boxes=prepare(world,{m:actor(world,m) for m in members},deliveries,response)
        else:
            boxes=_prepared_boxes(deliveries,response)
    except ValueError:
        return [wire.party_join_failed()]
    # Commit only after source/phase checks, encoding and bounded queue copies.
    world.invitations.pop(session)
    if party is None:
        party=after;world.next_party+=1;world.parties[party['id']]=party;world.party_of[inviter]=party
        world.bind_initial_party_invites(party,invite)
    else:
        party.update(dungeon=after['dungeon'],raid_party=after.get('raid_party',False))
        if after.get('union_party'):
            party.update(leader=after['leader'],union_groups=after['union_groups'])
        party['members'][:]=members;party['ready'].clear();party.pop('admission',None)
    world.party_of[session]=party;world.recruitment_candidates=pending
    for m,box in boxes.items():m.mailbox=box
    return response
