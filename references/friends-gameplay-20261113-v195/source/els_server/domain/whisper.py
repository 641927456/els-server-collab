"""Native whispers and authenticated relationship chat."""
from contextlib import closing
import sqlite3
from els_server.protocol import social_messages as wire


def handle(world,session,request,now):
    app=session.application
    players=tuple(app.playing.values())
    target=next((s for s in players if not s.released and s.role=='game'
        and s.phase in ('town_ready','dungeon_active','photo_zone_admitted',
                        'guild_agit_ready','wedding_hall') and not s.coop_error
        and app.playing.get(s.identity['id']) is s and app.registry.enabled(s.identity['id'])
        and s.account.character()['name']==request['recipient']),None)
    # Native name-based producer uses UINT64_MAX when no character UID was
    # selected. A supplied positive UID must identify that same live role.
    if (target is None or target is session
        or request['target_uid'] not in (0,2**64-1,target.account.uid)):
        return [wire.chat_ack(-1)]
    return _deliver(session,target,request['text'],4,now)


def relationship(session,request,now):
    # Client modes 8 and 9 both use relationship packet type 7.
    from els_server.domain.gameplay_announcements import ready
    from els_server.storage.relationships import snapshot
    app=session.application;actor=session.account
    if app.playing.get(actor.account_id) is not session or not app.registry.enabled(actor.account_id):
        return [wire.chat_ack(-1)]
    try:
        with closing(sqlite3.connect(actor.store.path)) as db, db:
            db.execute('BEGIN')
            saved=snapshot(db,actor.uid,actor.account_id)
            if saved is None or saved['kind'] not in (7,8):
                return [wire.chat_ack(-1)]
            if request['recipient'] not in ('',saved['peer_name']) or request['target_uid'] not in (0,2**64-1,saved['peer_uid']):
                return [wire.chat_ack(-1)]
            target=next((peer for account,peer in app.playing.items()
                         if peer.account.uid==saved['peer_uid'] and ready(peer) and app.registry.enabled(account)),None)
            if target is None:
                return [wire.chat_ack(-1)]
        return _deliver(session,target,request['text'],7,now)
    except (ValueError, sqlite3.Error):
        return [wire.chat_ack(-1)]


def _deliver(session,target,text,channel,now):
    from els_server.domain.party_commands import _prepared_boxes
    notice=wire.chat_notice(session.account.character(),session.identity['id'],
        text,channel,recipient=target.account.character())
    response=[wire.chat_ack()]
    # The world worker holds the sender's box. Protect the other box against
    # an independent worker draining or appending while it is being replaced.
    with target.mailbox.lock:
        boxes=_prepared_boxes([(session,[notice]),(target,[notice])],response)
        session.chat_times.append(now)
        for member,box in boxes.items():member.mailbox=box
    return response
