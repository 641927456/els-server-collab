"""Resolve an inspection request against a selected player on the same server."""

from time import time

from els_server.domain.equipment_engrave_flow import current_lease
from els_server.protocol import equipment_inspect_messages as wire
from els_server.storage.friend_state import character as find_character
from els_server.storage.inventory_state import load_equipped_items
from els_server.storage.luciel_state import active_state, state as style_state
from els_server.storage.read_scope import snapshot_connection
from els_server.storage.titles import equipped as equipped_title


def handle(session, event):
    if (
        session.client_build != 'dx11_260923'
        or not current_lease(session)
        or 0x28 not in session.completed
        or event.performers not in ((), (0,))
        or event.uid != event.target_uid
        or event.uid != 2**64 - 1
        or event.payload_mode != 0
    ):
        return [wire.acknowledgement()]

    app = session.application
    try:
        name, server = wire.request(event.payload)
        with snapshot_connection(session.account.store.path) as db:
            db.execute('BEGIN')
            target = find_character(db, name=name)
            account_id = target['account_id']
            uid = target['uid']
            peer = app.playing.get(account_id)
            if (
                peer is None
                or not current_lease(peer)
                or peer.account.uid != uid
                or 0x28 not in peer.completed
                or peer.phase in ('closing', 'channels_ready')
                or not app.registry.enabled(account_id)
            ):
                return [wire.acknowledgement()]

            character = peer.account.characters._identity(db, uid)
            character['title'] = equipped_title(db, uid)
            if character['unit_type'] == 10:
                character['luciel_active_unit'] = active_state(db, uid)['active_unit']
                character['luciel_style'] = style_state(db, uid)['style']
            # The inventory projection attaches the effective deadline.
            # Match the native expiry boundary even before the owner's sweep.
            now = int(time())
            items = [item for item in load_equipped_items(db, uid)
                     if item.get('expires_at', now) >= now]
    except ValueError:
        return [wire.acknowledgement()]

    return [wire.acknowledgement(character, items, server=server)]
