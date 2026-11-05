"""Authenticated normal-party selection; native UI and readiness consumers own presentation."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol import social_messages as wire


def select(world,session,event):
    ack=lambda result:[Event(0x201,kind=0x146,payload=struct.pack('>i',result))]
    party=world.party_of.get(session)
    if (event.event_id!=0x202 or session.released or session.phase!='town_ready'
        or session not in world.members or party is None or party['leader'] is not session
        or party['run'] is not None or party.get('solo_challenge') or party.get('challenge')
        or party.get('challenge_pending') or party.get('raid_party')):
        return ack(-1)
    # Original 2E0DA70 writes exactly int32, int8 difficulty, int8 mode.
    # Only the installed current normal selection (difficulty0/mode0) is admitted.
    if len(event.payload)!=6:return ack(-1)
    identity,difficulty,mode=struct.unpack('>ibb',event.payload)
    if difficulty!=0 or mode!=0:return ack(-1)
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.domain.raid_party import admission_size,raid_definition
    from els_server.domain.region_quests import account_dungeon_allowed
    identity=route_catalog().entry_identity(identity)
    members=tuple(party['members'])
    if (not route_catalog().supports(identity) or raid_definition(identity) is not None
        or not admission_size(party,identity)
        or any(s.released or s.phase!='town_ready' or s not in world.members
            or world.party_of.get(s) is not party or not account_dungeon_allowed(s.account,identity)
            for s in members)):
        return ack(-1)
    changed=(party['dungeon'],party.get('difficulty',0),party.get('mode',0))!=(identity,difficulty,mode)
    # 2D618E0 consumes this six-byte notice and updates the existing PartyManager.
    notice=Event(0x201,kind=0x147,payload=struct.pack('>ibb',identity,difficulty,mode))
    # Compile all packets before changing the selection/readiness/admission.
    notices=[notice]
    if changed:notices.extend(wire.party_ready_notice(s.account.uid,False) for s in members)
    response=ack(0)
    if changed:
        party.update(dungeon=identity,difficulty=difficulty,mode=mode)
        party['ready'].clear()
        party.pop('admission',None)
    # A repeated selection replays its native receipt without undoing newly ready peers.
    for other in members:
        for message in notices:world.send(other,message)
    return response
