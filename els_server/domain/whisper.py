"""Native channel4 online whispers. Formatting and reply UI remain client-owned."""
from els_server.protocol import social_messages as wire


def handle(world,session,request,now):
    from els_server.domain.party_commands import _prepared_boxes
    app=session.application
    players=tuple(app.playing.values())
    target=next((s for s in players if not s.released and s.role=='game'
        and s.phase in ('town_ready','dungeon_active') and not s.coop_error
        and app.playing.get(s.identity['id']) is s and app.registry.enabled(s.identity['id'])
        and s.account.character()['name']==request['recipient']),None)
    # Native name-based producer uses UINT64_MAX when no character UID was
    # selected. A supplied positive UID must identify that same live role.
    if (target is None or target is session
        or request['target_uid'] not in (0,2**64-1,target.account.uid)):
        return [wire.chat_ack(-1)]
    notice=wire.chat_notice(session.account.character(),session.identity['id'],
        request['text'],4,recipient=target.account.character())
    response=[wire.chat_ack()]
    boxes=_prepared_boxes([(session,[notice]),(target,[notice])],response)
    session.chat_times.append(now)
    for member,box in boxes.items():member.mailbox=box
    return response
