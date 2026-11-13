"""Authenticated normal-party selection; native UI and readiness consumers own presentation."""
import struct
from els_server.protocol.protocol_codec import Event


def available(party,identity):
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.raid_party import waiting_size,raid_definition
    from els_server.domain.region_quests import account_dungeon_allowed
    return (route_catalog().supports(identity)
        and bool(party.get('raid_party'))==(raid_definition(identity) is not None)
        and waiting_size(party,identity)
        and all(account_dungeon_allowed(s.account,identity)for s in party['members']))


def current_selection(identity,difficulty,mode):
    """Map both native current-route forms to the existing canonical selection."""
    from els_server.domain.dungeon_routes import route_catalog
    routes=route_catalog();selected=routes.entry_identity(identity)
    if mode:raise ValueError('Current party selection mode')
    if difficulty:
        from els_server.game_data import client_data
        # The original button re-submits an admitted concrete route using its
        # resource difficulty (e.g.30242/2), while manual icons use a base ID/0.
        # Superseded difficulty IDs remain aliases only for the current icon/0.
        if (identity!=selected or not routes.supports(identity)
            or difficulty!=client_data().dungeon(identity).get('difficulty')):
            raise ValueError('Current party selection difficulty')
    return selected,0,0


def select(world,session,event):
    ack=lambda result:[Event(0x201,kind=0x146,payload=struct.pack('>i',222 if result==-1 else result))]
    party=world.party_of.get(session)
    if (event.event_id!=0x202 or session.released or session.phase!='town_ready'
        or session not in world.members or party is None or party['leader'] is not session
        or party['run'] is not None or party.get('solo_challenge') or party.get('challenge')
        or party.get('challenge_pending')):
        return ack(2)
    # Original 2E0DA70 writes exactly int32, int8 difficulty, int8 mode.
    if len(event.payload)!=6:return ack(2)
    identity,difficulty,mode=struct.unpack('>ibb',event.payload)
    native_difficulty=difficulty
    try:identity,difficulty,mode=current_selection(identity,difficulty,mode)
    except ValueError:return ack(2)
    members=tuple(party['members'])
    if (not available(party,identity)
        or any(s.released or s.phase!='town_ready' or s not in world.members
            or world.party_of.get(s) is not party
            for s in members)):
        return ack(2)
    changed=(party['dungeon'],party.get('difficulty',0),party.get('mode',0))!=(identity,difficulty,mode)
    # 2D618E0 updates the native PartyManager. Preserve the resource difficulty
    # from145; returning canonical0 makes the original UI re-submit indefinitely.
    notice=Event(0x201,kind=0x147,payload=struct.pack('>ibb',identity,native_difficulty,mode))
    # Prepare actual bounded delivery before changing selection/readiness.
    notices=[notice]
    response=ack(0)
    from els_server.domain.party_commands import _prepared_boxes
    from els_server.domain.local_session import SessionOrderError
    try:boxes=_prepared_boxes([(other,notices)for other in members],response)
    except SessionOrderError:return ack(2)
    if changed:
        party.update(dungeon=identity,difficulty=difficulty,mode=mode)
        party['ready'].clear()
        party.pop('admission',None)
    # A repeated selection replays its native receipt without undoing newly ready peers.
    for other,box in boxes.items():other.mailbox=box
    if changed:
        from els_server.domain.party_entry_consent import cancel
        cancel(world.dungeons,party)
    return response
