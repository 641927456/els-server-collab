"""Native waiting-party commands. UI, effects and combat remain client-owned."""
import copy
import struct
from collections import deque
from els_server.protocol import social_messages as wire
from els_server.protocol.protocol_codec import Event,encode_event


def selection_context(party):
    return (party['leader'],tuple(party['members']),party['dungeon'],
        party.get('difficulty',0),party.get('mode',0),frozenset(party['ready']))


def _prepared_boxes(deliveries,response):
    # Use the actual transport encoder and bounded mailboxes before any mutation.
    for event in response:encode_event(event)
    boxes={}
    for session,events in deliveries:
        box=boxes.get(session)
        if box is None:
            box=copy.copy(session.mailbox)
            box.messages=deque(session.mailbox.messages)
            box.moves=dict(session.mailbox.moves)
            boxes[session]=box
        for event in events:
            encode_event(event)
            box.append(event)
    return boxes


def _forget_invitations(world,party,old_leader):
    world.invitations={s:v for s,v in world.invitations.items()
        if v.get('party') is not party and v.get('inviter') is not old_leader}


def handle(world,session,event):
    kind=event.kind
    if event.event_id!=0x202 or kind not in (0x14e,0x151):return None
    ack=lambda result:[Event(0x201,kind=kind+1,payload=struct.pack('>i',result))]
    party=world.party_of.get(session)
    if (session.released or session.phase!='town_ready' or session not in world.members
        or party is None or party['leader'] is not session or party['run'] is not None
        or any(party.get(k) for k in ('solo_challenge','challenge','challenge_pending','raid_party'))
        or len(event.payload)!=8 or event.payload_mode!=0):return ack(-1)
    members=tuple(party['members'])
    if (not 2<=len(members)<=4 or any(m.released or m.phase!='town_ready'
        or m not in world.members or world.party_of.get(m) is not party
        or world.dungeons.room(m) is not None for m in members)):return ack(-1)
    from els_server.domain.party_recruitment import waiting,signature,removal_plan
    from els_server.domain.avatar_set_flow import validate
    from els_server.domain.dungeon_equipment_loot_flow import current_lease
    try:recruitment_actors=waiting(world,party) if party.get('recruitment') else {}
    except ValueError:return ack(-1)
    recruitment_before=signature(world)
    recruitment_pending,recruitment_notices=removal_plan(world,party=party)
    def validate_recruitment():
        try:
            if recruitment_actors:
                if signature(world)!=recruitment_before:return False
                for member,captured in recruitment_actors.items():
                    validate(member,captured)
                    if (not current_lease(member) or not member.application.registry.enabled(member.account.account_id)
                        or member.account.character().get('pending_delete')):return False
            return True
        except ValueError:return False
    uid=struct.unpack('>Q',event.payload)[0]
    target=next((m for m in members if m.account.uid==uid),None)
    if target is None:return ack(-1)
    if kind==0x14e:
        if target is session:return ack(0)
        from els_server.domain.dungeon_routes import route_catalog
        from els_server.domain.raid_party import admission_size,raid_definition
        from els_server.domain.region_quests import account_dungeon_allowed
        identity=route_catalog().entry_identity(party['dungeon'])
        if (not route_catalog().supports(identity) or raid_definition(identity) is not None
            or not party.get('recruitment') and not admission_size(party,identity)
            or not all(account_dungeon_allowed(m.account,identity) for m in members)):
            return ack(-1)
        if party.get('recruitment'):
            from els_server.domain.party_recruitment import source
            try:source(party)
            except ValueError:return ack(-1)
        # Native2D65350: previous UID, new UID, regroup=false.
        changed=Event(0x201,kind=0x150,payload=struct.pack('>QQB',session.account.uid,uid,0))
        notices=[changed,*[wire.party_ready_notice(m.account.uid,False) for m in members]]
        response=ack(0);boxes=_prepared_boxes([*recruitment_notices,*[(m,notices) for m in members]],response)
        if not validate_recruitment():return ack(-1)
        party['leader']=target;party['ready'].clear();party.pop('admission',None)
        _forget_invitations(world,party,session)
    else:
        if target is session:return ack(-1)
        remaining=[m for m in members if m is not target]
        response=ack(0)
        # Reuse the installed leave/reset+snapshot protocol and its two-member
        # close policy. No persistent account ban or player-data deletion.
        removed=wire.party_removed(uid)
        if len(remaining)<2 and not party.get('recruitment'):
            deliveries=[(m,[removed]) for m in members]
        else:
            after={**party,'members':remaining,'ready':set()}
            from els_server.domain.normal_party import roster_events
            notices=roster_events(after,reset=True)
            deliveries=[(target,[removed]),*[(m,notices) for m in remaining]]
        boxes=_prepared_boxes([*recruitment_notices,*deliveries],response)
        if not validate_recruitment():return ack(-1)
        party['members'][:]=remaining;party['ready'].clear();party.pop('admission',None)
        world.party_of.pop(target,None)
        if len(remaining)<2 and not party.get('recruitment'):
            for m in remaining:world.party_of.pop(m,None)
            world.parties.pop(party['id'],None)
        _forget_invitations(world,party,session)
    world.recruitment_candidates=recruitment_pending
    for m,box in boxes.items():m.mailbox=box
    return response
