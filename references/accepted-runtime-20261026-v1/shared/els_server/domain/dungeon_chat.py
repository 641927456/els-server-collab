"""Route existing native ordinary chat only inside its admitted shared run."""
from els_server.protocol import social_messages as wire


def handle(world,session,text,now):
    from els_server.domain.normal_party import ordinary
    from els_server.domain.party_commands import _prepared_boxes
    party=world.party_of.get(session)
    room=world.dungeons.room(session)
    if party is None and room is None:
        from els_server.domain.solo_chat import handle as solo
        return solo(world,session,text,now)
    if (party is None or not ordinary(party) or room is None
        or world.parties.get(party['id']) is not party
        or room.party is not party or party['run'] is not room
        or room.phase not in ('active','part_end','clear')):
        return [wire.chat_ack(-1)]
    app=session.application

    def current(member):
        return (member in party['members'] and world.party_of.get(member) is party
            and world.dungeons.room(member) is room and not member.released
            and member.role=='game' and member.phase=='dungeon_active'
            and not member.coop_error and not member.dungeon_return_pending
            and app.playing.get(member.identity['id']) is member
            and app.registry.enabled(member.identity['id']))

    recipients=[member for member in room.members if current(member)]
    if session not in recipients:return [wire.chat_ack(-1)]
    notice=wire.chat_notice(session.account.character(),session.identity['id'],text,0)
    response=[wire.chat_ack()]
    boxes=_prepared_boxes([(member,[notice]) for member in recipients],response)
    session.chat_times.append(now)
    for member,box in boxes.items():member.mailbox=box
    return response
