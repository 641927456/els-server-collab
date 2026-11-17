"""Server-owned text for the existing native bottom megaphone panel."""
import functools
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from els_server.protocol.native_notice_messages import notice
from els_server.protocol.server_announcement_messages import announcement
from els_server.protocol.protocol_codec import encode_event


_settings_path = None


def configure(path):
    global _settings_path
    _settings_path = Path(path)
    _compiled_policy.cache_clear()


def _text(value, maximum):
    if (not isinstance(value, str) or not value.strip()
            or len(value.encode('utf-16le')) > maximum * 2
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Invalid server announcement text')
    return value


def _validate(data):
    if not isinstance(data, dict) or set(data) != {'sender', 'interval_seconds', 'messages'}:
        raise ValueError('Invalid server announcements policy')
    sender = _text(data['sender'], 24)
    interval = data['interval_seconds']
    if type(interval) is not int or interval < 1:
        raise ValueError('Invalid server announcement interval')
    if not isinstance(data['messages'], list) or len(data['messages']) > 20:
        raise ValueError('Invalid server announcement list')
    events = tuple(announcement(sender, _text(text, 200)) for text in data['messages'])
    for event in events:
        encode_event(event)
    return sender, interval, tuple(data['messages']), events


def _revision(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


@functools.lru_cache(maxsize=1)
def _compiled_policy():
    path = _settings_path
    if path is None or not path.exists():
        path = Path(__file__).resolve().parents[1] / 'data/server_announcements.json'
    data = json.loads(path.read_bytes())
    return (*_validate(data), _revision(data))


def policy():
    _, interval, _, events, _ = _compiled_policy()
    return interval, events


def snapshot():
    sender, interval, messages, _, revision = _compiled_policy()
    return dict(sender=sender, interval_seconds=interval, messages=list(messages), revision=revision)


def update(settings, expected_revision):
    if _settings_path is None:
        raise ValueError('常驻公告配置尚未初始化')
    _validate(settings)
    if any('<' in text or '>' in text or '#c' in text.casefold()
           for text in (settings['sender'], *settings['messages'])):
        raise ValueError('常驻公告只接受纯文本')
    if snapshot()['revision'] != expected_revision:
        raise ValueError('常驻公告已被更新，请重新载入后再保存')
    _settings_path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', newline='\n',
                                         dir=_settings_path.parent, delete=False) as stream:
            name = Path(stream.name)
            json.dump(settings, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        name.replace(_settings_path)
    finally:
        if name is not None:
            name.unlink(missing_ok=True)
    _compiled_policy.cache_clear()
    return snapshot()


def periodic(session):
    if (session.client_build != 'dx11_260923' or session.role != 'game'
            or getattr(session, 'released', False)
            or session.phase not in ('town_ready', 'dungeon_active')
            or session.phase == 'dungeon_active' and not session.dungeon_substage_synced):
        return []
    _, interval, _, events, _ = _compiled_policy()
    if not events:
        return []
    actor = (session.shop_session_id, session.account.uid)
    previous = getattr(session, '_server_announcement', None)
    now = time.monotonic()
    if previous is None or previous[0] != actor or previous[3] is not events:
        index = 0
    else:
        _, deadline, index, _ = previous
        if now < deadline:
            return []
    event = events[index]
    session._server_announcement = (actor, now + interval, (index + 1) % len(events), events)
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
