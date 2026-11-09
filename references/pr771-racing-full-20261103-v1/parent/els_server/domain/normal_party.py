"""Server-owned ordinary room state; original13B and147 own client rendering."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol import social_messages as wire


def ordinary(party):
    return not any(party.get(k) for k in ('raid_party','solo_challenge','challenge','challenge_pending'))


def roster_events(party,reset=False):
    events=([wire.party_removed()] if reset else [])+[wire.party_snapshot(party)]
    # Original2D59FA0 installs13B then overwrites its map with local UI state.
    # Original2D618E0's147 reapplies the canonical server selection afterwards.
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.raid_party import raid_definition
    if (ordinary(party) and route_catalog().supports(party['dungeon'])
        and raid_definition(party['dungeon']) is None
        and party.get('difficulty',0)==0 and party.get('mode',0)==0):
        events.append(Event(0x201,kind=0x147,payload=struct.pack('>ibb',party['dungeon'],party.get('difficulty',0),party.get('mode',0))))
    return events


def invite_selection(world,session,target,party,request):
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.raid_party import admission_size,raid_definition
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
    elif not admission_size(proposed,identity) or any(not account_dungeon_allowed(m.account,identity) for m in members):return None
    return selected


def accept(world,session,invite):
    from els_server.domain.party_commands import _prepared_boxes
    from els_server.domain.raid_party import admission_size
    from els_server.domain.region_quests import account_dungeon_allowed
    inviter=invite['inviter'];party=invite['party'];selection=invite.get('ordinary_selection')
    denied=lambda:[wire.party_answer_ack(result=-1)]
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
    elif not admission_size(after,selection[0]) or any(not account_dungeon_allowed(m.account,selection[0]) for m in members):return denied()
    after.pop('admission',None)
    response=[wire.party_answer_ack(inviter.account.uid)]
    notices=roster_events(after,reset=party is not None)
    from els_server.domain.party_recruitment import removal_plan,prepare,actor
    from els_server.domain.raid_party import capacity
    recruitment_pending,recruitment_notices=removal_plan(world,applicant=session,party=party if party is not None and party.get('recruitment') and len(members)>=capacity(after) else None)
    deliveries=[*recruitment_notices,*[(m,notices) for m in members]]
    recruitment_related=bool(after.get('recruitment') or recruitment_notices)
    boxes=prepare(world,{m:actor(world,m) for m in members},deliveries,response) if recruitment_related else _prepared_boxes(deliveries,response)
    # Commit only after source/phase checks, encoding and bounded queue copies.
    world.invitations.pop(session)
    if party is None:
        party=after;world.next_party+=1;world.parties[party['id']]=party;world.party_of[inviter]=party
    else:
        party['members'][:]=members;party['ready'].clear();party.pop('admission',None)
    world.party_of[session]=party;world.recruitment_candidates=recruitment_pending
    for m,box in boxes.items():m.mailbox=box
    return response
