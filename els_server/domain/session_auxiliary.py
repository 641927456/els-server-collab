"""Recognize the existing no-op without running activity persistence per packet."""


def friends_auxiliary_noop(session, event):
    return (session.client_build == 'dx11_260923' and session.role == 'game'
            and session.phase in ('town_ready', 'dungeon_active')
            and event.event_id == 0x202 and event.kind == 0x7d0
            and event.performers == (0,) and event.uid == event.target_uid == 2**64-1
            and event.payload_mode == 0 and len(event.payload) == 9
            and session.application.playing.get(session.identity['id']) is session
            and session.account.store is not None
            and session.account.store.uid == session.account.uid)


def auxiliary_call(function, args):
    from els_server.application import FriendsSession
    from els_server.domain.local_session import LocalSession
    from els_server.protocol.protocol_codec import Event

    session = getattr(function, '__self__', None)
    if (type(session) not in (LocalSession, FriendsSession)
            or getattr(function, '__func__', None) is not type(session).handle
            or len(args) != 1 or type(args[0]) is not Event):
        return False
    if type(session) is FriendsSession:
        return (not session.released and not session.social_overflow
                and not session.coop_error and friends_auxiliary_noop(session, args[0]))
    # Only the materialized LOCAL handler with its existing actor binding may
    # omit this work. Root/historical handlers keep their ordinary admission.
    if 'local_auxiliary_noop' not in LocalSession.handle.__code__.co_names:
        return False
    from els_server.performance import local_auxiliary_noop
    return local_auxiliary_noop(session, args[0])
