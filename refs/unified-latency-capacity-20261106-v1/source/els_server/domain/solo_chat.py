"""Echo native ordinary chat only to its authenticated admitted solo actor."""
from els_server.protocol import social_messages as wire


def handle(world,session,text,now):
    from els_server.domain.party_commands import _prepared_boxes
    app=session.application
    if (session.released or session.role!='game' or session.phase!='dungeon_active'
        or session.coop_error or session.dungeon_return_pending
        or not session.dungeon_substage_synced
        or app.playing.get(session.identity['id']) is not session
        or not app.registry.enabled(session.identity['id'])
        or session in world.party_of or world.dungeons.room(session) is not None
        or world.field_bosses.room(session) is not None):
        return [wire.chat_ack(-1)]
    # Reuse the existing solo relay admission gate, including the server-created
    # UUID4 run, current playing actor and singleton participant identity.
    admitted=world.dungeons.manifest(app,session.identity['id'])
    if (admitted is None or admitted['uid']!=session.account.uid
        or admitted['peers']!=[dict(uid=session.account.uid,port=21100)]):
        return [wire.chat_ack(-1)]
    notice=wire.chat_notice(session.account.character(),session.identity['id'],text,0)
    response=[wire.chat_ack()]
    boxes=_prepared_boxes([(session,[notice])],response)
    session.chat_times.append(now)
    session.mailbox=boxes[session]
    return response
