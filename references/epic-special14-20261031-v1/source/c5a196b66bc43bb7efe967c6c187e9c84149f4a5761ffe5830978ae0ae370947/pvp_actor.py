"""Original actor/world bindings for the finite current real-player PvP flow.

Qualification and failure-reply identity are separate. Keep strong object
references and recheck values after all encoders, including failed replies.
The existing Application worker remains the sole owner of in-memory changes.
"""
from pathlib import Path
import json
import sqlite3
from els_server.domain.equipment_engrave_flow import current_lease


class Binding:
    def __init__(self, refs, values):
        self.refs, self.values = refs, values

    def __eq__(self, other):
        return (type(other) is Binding and self.values == other.values
                and len(self.refs) == len(other.refs)
                and all(a is b for a, b in zip(self.refs, other.refs)))


def actor(world, s):
    a = s.account
    app = s.application
    root = a.root
    if (s.released or s.social_overflow or s.coop_error or not current_lease(s)
            or s.role != 'game' or s.client_build != 'dx11_260923'
            or not s.item_test or 0x28 not in s.completed
            or app.world is not world or not app.registry.enabled(a.account_id)
            or a.store.uid != a.uid or a.characters.account_id != a.account_id
            or root.root is not root or root.characters is not a.characters
            or root.account_id != a.account_id or s.identity['id'] != a.account_id):
        raise ValueError('PvP original enabled selected actor')
    town_key = world.members.get(s)
    town = world.towns.get(town_key)
    room = getattr(world, 'pvp', None)
    pvp_room = room.room(s) if room is not None else None
    refs = (s, a, a.store, a.characters, root, root.character_accounts,
        root.characters, getattr(root, 'store', None), app, app.config,
        app.accounts, app.playing, s.identity, app.registry, world,
        world.dungeons, world.dungeons.room(s), world.members, world.towns,
        town, None if town is None else town.get(s), s.dungeon_run,
        world.party_of, world.party_of.get(s), room, pvp_room, s.mailbox,
        None if room is None or room.support_binding(s)is None else room.support_binding(s)[0])
    values = (a.account_id, a.uid, a.store.uid, a.characters.account_id,
        root.account_id, s.role, s.phase, s.client_build, s.item_test,
        s.shop_session_id, s.active_map, s.pending_map, s.enter_town,
        s.dungeon_return_pending, s.dungeon_id, s.released,
        frozenset(s.completed), town_key,
        str(Path(a.store.path).resolve()), str(Path(a.characters.path).resolve()),
        str(Path(app.config.state_file).resolve()), str(Path(app.registry.path).resolve()),
        json.dumps(s.identity, sort_keys=True),
        json.dumps(a.get_location(), sort_keys=True),
        tuple(s.mailbox.messages), tuple(s.mailbox.moves.items()), s.mailbox.bytes,
        None if room is None else room.support_binding(s))
    return Binding(refs, values)


def capture(world, s):
    before = actor(world, s)
    def guard():
        if actor(world, s) != before:
            raise ValueError('PvP original actor/source changed')
    return guard


def safe_capture(world, s):
    try:
        return capture(world, s)
    except (ValueError, AttributeError, KeyError, TypeError, sqlite3.Error):
        return None


def failed(guard, encode):
    if guard is None:
        return []
    try:
        guard()
        events = encode()
        guard()
        from els_server.protocol.protocol_codec import encode_event
        for event in events:
            encode_event(event)
        guard()
        return events
    except (ValueError, AttributeError, KeyError, TypeError, UnicodeError,
            OverflowError, sqlite3.Error):
        return []


def town(world, s):
    from els_server.storage.local_state import TOWN_SCENES
    before = actor(world, s)
    if not world.pvp.support_ready(s):raise ValueError('Official arena requires verified current native HP support')
    location = s.account.get_location()
    map_id = location['map']
    c = s.account.character()
    if (s.phase != 'town_ready' or not s.enter_town or s.dungeon_return_pending
            or s.pending_map != map_id or s.active_map != map_id
            or map_id not in TOWN_SCENES or not {0x225, 0x227}.issubset(s.completed)
            or world.members.get(s) != (1, map_id)
            or s not in world.towns.get((1, map_id), {})
            or world.dungeons.transport_room(s) is not None
            or s in world.party_of or c['uid'] != s.account.uid
            or c.get('pending_delete') or c['level'] < 10):
        raise ValueError('PvP normal solo town registration')
    return before
