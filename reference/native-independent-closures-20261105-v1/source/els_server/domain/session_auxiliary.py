"""Recognize the existing no-op without running activity persistence per packet."""
import time


def friends_auxiliary_session(session):
    return (session.client_build == 'dx11_260923' and session.role == 'game'
            and session.phase in ('town_ready', 'dungeon_active', 'photo_zone_admitted', 'photo_zone_lobby')
            and session.application.playing.get(session.identity['id']) is session
            and session.account.store is not None
            and session.account.store.uid == session.account.uid)


def auxiliary_envelope(event):
    return (event.event_id == 0x202 and event.kind == 0x7d0
            and event.performers == (0,) and event.uid == event.target_uid == 2**64-1
            and event.payload_mode == 0 and len(event.payload) == 9)


def friends_auxiliary_noop(session, event):
    return auxiliary_envelope(event) and friends_auxiliary_session(session)


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


def activity_due(function,args=()):
    """Use the Friends periodic handler's existing one-second activity gate."""
    from els_server.application import FriendsSession
    session = getattr(function, '__self__', None)
    if (getattr(function,'__name__',None)=='handle' and len(args)==1
            and maintenance_request(session,args[0])):
        return False
    if (type(session) is FriendsSession
            and getattr(function, '__func__', None) is FriendsSession.periodic_notifications):
        return time.monotonic() >= session.next_periodic
    return True


# These packets update only native live/capability state, or are currently
# unconsumed. Their original handlers and authentication still run. Loaded
# dungeon upkeep already has an independent periodic path; none changes the
# activity clock's scene/eligibility. D0 grants coins, food or inventory, never
# character EXP/class/scene. Its economic writer still commits synchronously;
# attendance/title spans use the existing periodic, identity-change and close
# observations instead of two extra clock passes for every ground item.
MAINTENANCE_KINDS=frozenset((0x640,0x3e6,0x38e,0xff20,0xff21,0xd0))


def maintenance_request(session,event):
    from els_server.protocol.protocol_codec import Event
    from els_server.domain.local_session import LocalSession
    return (isinstance(session,LocalSession) and type(event) is Event and event.event_id==0x202
            and event.kind in MAINTENANCE_KINDS
            and session.client_build=='dx11_260923' and session.role=='game'
            and session.phase=='dungeon_active' and session.dungeon_substage_synced
            and not session.part_end_notified and not session.gate_stage_loading
            and not session.clear_notified and not getattr(session,'dungeon_failed',False))


def maintenance_reply(session,event,replies):
    if not maintenance_request(session,event):return False
    # Item/source loot, level/quest rewards and every other emitted state
    # retain the complete original synchronization pipeline. Coins/food's D2
    # and D1 ACK are the direct committed result, not activity/UI changes.
    return (all(e.event_id==0x201 and e.kind in (0xd1,0xd2)for e in replies)
            if event.kind==0xd0 else not replies)
