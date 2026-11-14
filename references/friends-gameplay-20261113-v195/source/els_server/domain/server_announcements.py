"""Server-owned text for the existing native bottom megaphone panel."""
import functools
import json
import time
from pathlib import Path
from els_server.protocol.native_notice_messages import notice
from els_server.protocol.server_announcement_messages import announcement
from els_server.protocol.protocol_codec import encode_event


def _text(value, maximum):
    if (not isinstance(value, str) or not value.strip()
            or len(value.encode('utf-16le')) > maximum * 2
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Invalid server announcement text')
    return value


@functools.lru_cache(maxsize=1)
def policy():
    data = json.loads((Path(__file__).resolve().parents[1]
                       / 'data/server_announcements.json').read_bytes())
    if set(data) != {'sender', 'interval_seconds', 'messages'}:
        raise ValueError('Invalid server announcements policy')
    sender = _text(data['sender'], 24)
    interval = data['interval_seconds']
    if type(interval) is not int or interval < 1:
        raise ValueError('Invalid server announcement interval')
    if not isinstance(data['messages'], list):
        raise ValueError('Invalid server announcement list')
    events = tuple(announcement(sender, _text(text, 200)) for text in data['messages'])
    for event in events:
        encode_event(event)
    return interval, events


def periodic(session):
    if (session.client_build != 'dx11_260923' or session.role != 'game'
            or getattr(session, 'released', False)
            or session.phase not in ('town_ready', 'dungeon_active')
            or session.phase == 'dungeon_active' and not session.dungeon_substage_synced):
        return []
    interval, events = policy()
    if not events:
        return []
    actor = (session.shop_session_id, session.account.uid)
    previous = getattr(session, '_server_announcement', None)
    now = time.monotonic()
    if previous is None or previous[0] != actor:
        index = 0
    else:
        _, deadline, index = previous
        if now < deadline:
            return []
    event = events[index]
    session._server_announcement = (actor, now + interval, (index + 1) % len(events))
    return [event]


def dungeon_closing(session):
    deadline = getattr(session, 'challenge_deadline', None)
    if (deadline is None or session.client_build != 'dx11_260923' or session.phase != 'dungeon_active'
            or session.clear_notified or not session.dungeon_substage_synced):
        return []
    remaining = deadline - time.time()
    if not 0 < remaining <= 120:
        return []
    variant = 0 if remaining <= 10 else 1 if remaining <= 60 else 2
    key = (session.reward_run_id, deadline, variant)
    if getattr(session, '_challenge_close_notice', None) == key:
        return []
    session._challenge_close_notice = key
    return [notice(22, '', variant=variant)]
