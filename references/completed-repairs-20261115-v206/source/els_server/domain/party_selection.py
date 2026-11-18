"""Authenticated normal-party selection; native UI and readiness consumers own presentation."""
import struct
from els_server.protocol.protocol_codec import Event


def available(party,identity):
    return selection_result(party,identity)[0]==0


def selection_result(party,identity,*,retained=False):
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.raid_party import waiting_size,raid_definition,capacity
    from els_server.domain.region_quests import account_dungeon_allowed
    if not route_catalog().supports(identity):return 222,'unsupported_route'
    raid=raid_definition(identity) is not None
    mismatch=bool(party.get('raid_party'))!=raid
    if mismatch and not retained:
        return (2158,'requires_raid_party') if raid else (2153,'requires_normal_party')
    # A45/A47 changes type/capacity and deliberately retains the old selection.
    # A repeated145 synchronizes that selection; it grants no entry authority.
    size_ok=1<=len(party['members'])<=capacity(party) if mismatch else waiting_size(party,identity)
    if not size_ok:return 215,'party_capacity'
    if not all(account_dungeon_allowed(s.account,identity)for s in party['members']):
        return 2224,'member_qualification'
    return 0,'eligible'


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
    party=world.party_of.get(session)
    diagnostic=dict(selection_path='ordinary',selection_is_leader=bool(party and party['leader'] is session),
        selection_raid_party=bool(party and party.get('raid_party')))
    def ack(result,reason):
        session._party_selection_diagnostic=(event,dict(diagnostic,selection_reason=reason))
        return [Event(0x201,kind=0x146,payload=struct.pack('>i',result))]
    if (event.event_id!=0x202 or session.released or session.phase!='town_ready'
        or session not in world.members):return ack(2,'actor_state')
    if party is None:return ack(211,'no_party')
    if party['leader'] is not session:return ack(225,'not_leader')
    if (party['run'] is not None or party.get('solo_challenge') or party.get('challenge')
        or party.get('challenge_pending')):
        return ack(2,'party_busy')
    # Original 2E0DA70 writes exactly int32, int8 difficulty, int8 mode.
    if len(event.payload)!=6 or event.payload_mode!=0:return ack(222,'request_shape')
    identity,difficulty,mode=struct.unpack('>ibb',event.payload)
    diagnostic.update(selection_request_dungeon=identity,selection_request_difficulty=difficulty,selection_request_mode=mode)
    native_difficulty=difficulty
    try:identity,difficulty,mode=current_selection(identity,difficulty,mode)
    except ValueError:return ack(1406 if mode else 222,'request_mode' if mode else 'request_difficulty')
    diagnostic['selection_canonical_dungeon']=identity
    members=tuple(party['members'])
    if any(s.released or s.phase!='town_ready' or s not in world.members
            or world.party_of.get(s) is not party
            for s in members):
        return ack(1445,'member_state')
    changed=(party['dungeon'],party.get('difficulty',0),party.get('mode',0))!=(identity,difficulty,mode)
    result,reason=selection_result(party,identity,retained=not changed)
    if result:return ack(result,reason)
    # 2D618E0 updates the native PartyManager. Preserve the resource difficulty
    # from145; returning canonical0 makes the original UI re-submit indefinitely.
    notice=Event(0x201,kind=0x147,payload=struct.pack('>ibb',identity,native_difficulty,mode))
    # Prepare actual bounded delivery before changing selection/readiness.
    notices=[notice]
    response=ack(0,'selection_changed' if changed else 'selection_replay')
    from els_server.domain.party_commands import _prepared_boxes
    from els_server.domain.local_session import SessionOrderError
    try:boxes=_prepared_boxes([(other,notices)for other in members],response)
    except SessionOrderError:return ack(2,'mailbox_capacity')
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
