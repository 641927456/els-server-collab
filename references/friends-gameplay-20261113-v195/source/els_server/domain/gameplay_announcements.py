"""Publish committed game achievements through the original client UI."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging

from els_server.protocol.native_notice_messages import achievement
from els_server.protocol.protocol_codec import encode_event


_pending = ContextVar('gameplay_announcements', default=None)
_logger = logging.getLogger(__name__)
ENHANCEMENT_MINIMUM = 12
REFORGE_LEVEL = 21
RESONANCE_INTERVAL = 100
# Original weapon and accessory rewards in the existing formal Raid pool.
# Announce the award of the rare box, once. Opening the same box is not a new drop.
RARE_RAID_ITEMS = frozenset((
    135902, 136054, 136106, 136180,
    30615, 30616, 30617, 136052, 136053, 136107, 136108,
    136172, 136173, 136176, 136177, 136178, 30872, 30873,
    30874, 30875,
))
# The six live random Atma accessory boxes each yield one of these five
# native rare pieces. Keep their whitelist separate from Raid drops.
RANDOM_RARE_ITEMS = RARE_RAID_ITEMS | frozenset(range(30780, 30810))
RAID_CLEAR_TYPES = {'rosso': 21, 'berthe': 24, 'abyss': 25,
                    'conductor': 29, 'barkat': 30, 'marcus': 32}


def ready(session):
    return (not session.released and session.role == 'game'
            and session.client_build == 'dx11_260923'
            and not session.social_overflow and not session.coop_error
            and (session.phase in ('town_ready', 'guild_agit_ready', 'housing_ready',
                                   'photo_zone_admitted', 'wedding_hall') or
                 session.phase == 'dungeon_active' and session.dungeon_substage_synced))


def broadcast(app, events):
    for event in events:
        encode_event(event)
    delivered = failed = 0
    for account, session in app.playing.copy().items():
        with session.mailbox.lock:
            if app.playing.get(account) is not session or not ready(session):
                continue
            if not session.mailbox.try_extend(events):
                failed += 1
                continue
            delivered += 1
    return delivered, failed


@contextmanager
def collect():
    """Flush after the worker releases its actor, room and world locks."""
    pending = []
    token = _pending.set(pending)
    try:
        yield
    finally:
        _pending.reset(token)
        for app, events in pending:
            _, failed = broadcast(app, events)
            if failed:
                _logger.warning('Game announcement omitted for %d full mailboxes', failed)


def publish(session, events):
    app = getattr(session, 'application', None)
    if not events or app is None:
        return
    pending = _pending.get()
    if pending is None:
        broadcast(app, tuple(events))
    else:
        pending.append((app, tuple(events)))


def character_name(db, owner):
    return db.execute('SELECT name FROM characters WHERE uid=?', (owner,)).fetchone()[0]


def enhancement(db, owner, template, previous, level):
    if level > previous and level >= ENHANCEMENT_MINIMUM:
        return achievement(5, character_name(db, owner), template, level, 0)
    return None


def reforge(db, owner, template, level):
    if level == REFORGE_LEVEL:
        return achievement(23, character_name(db, owner), template, level)
    return None


def profession(db, owner, state):
    if state.level == 10:
        return [achievement({1: 15, 2: 16, 3: 17}[state.profession], character_name(db, owner))]
    return []


def guild_level(saved, before_experience):
    from els_server.domain.guild_rules import level

    after_experience = saved['system']['experience']
    if after_experience <= before_experience:
        return []
    after_level = level(after_experience)
    if after_level > level(before_experience):
        return [achievement(8, saved['name'], after_level)]
    return []


def progression(db, owner, *, ordinary=None, resonance=None):
    events = []
    if ordinary and ordinary[0] < 99 <= ordinary[1]:
        events.append(achievement(4, character_name(db, owner), 99))
    if resonance and not resonance['replayed'] and resonance['effective']:
        from els_server.domain.resonance import curve

        thresholds = curve()
        last = len(thresholds) // RESONANCE_INTERVAL * RESONANCE_INTERVAL
        levels = range(last, 0, -RESONANCE_INTERVAL)
        for milestone in levels:
            threshold = thresholds[milestone-1]['TOTAL_ER_EXP']
            if resonance['before'] < threshold <= resonance['after']:
                events.append(achievement(33, character_name(db, owner), milestone))
                break
    return events


def rare_raid_awards(db, owner, receipt, *, source_item=0):
    if receipt['replayed']:
        return []
    allowed = RANDOM_RARE_ITEMS if source_item else RARE_RAID_ITEMS
    templates = sorted({item['template'] for item in receipt.get('items', ())} & allowed)
    if not templates:
        return []
    name = character_name(db, owner)
    kind = 2 if source_item else 3
    return [achievement(kind, name, template, source_item=source_item) for template in templates]


def raid_clear(db, members, definition, dungeon):
    if (len(members) < 2 or not definition['final_map']
            or definition['mode'] not in ('normal', 'hard')):
        return []
    names = '、'.join(character_name(db, session.account.uid) for session in members)
    return [achievement(RAID_CLEAR_TYPES[definition['family']], names, dungeon=dungeon)]


def striker_clear(db, members, state, dungeon):
    if not state['complete'] or state['challenge'] not in (4, 5):
        return []
    names = '、'.join(character_name(db, session.account.uid) for session in members)
    # The native client resolves this encounter to its challenge family and
    # phase, then selects the red or orange localization itself.
    return [achievement(27, names, dungeon=dungeon)]
