"""The original item-funded megaphone and its single published channel."""
from contextlib import closing
import sqlite3
import struct

from els_server.domain.gameplay_announcements import character_name, publish, ready
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.protocol.server_announcement_messages import announcement
from els_server.protocol.social_messages import Reader


# Individually identified use items in this build. Gift packs are excluded.
SMALL = frozenset((212350, 80000119))
LARGE = frozenset((212360, 162035, 163129, 297079, 301367, 305689, 8200067, 80000120))
TEMPLATES = SMALL | LARGE


def definitions():
    from els_server.game_data import client_data

    data = client_data()
    for template in sorted(TEMPLATES):
        item = data.item(template)
        stack, = struct.unpack_from('<I', item['record'], 16)
        if (item['item_type'], item['flags8'], item['metadata']) != (7, 56, 2):
            raise ValueError('Megaphone native item definition changed')
        yield template, (2, 4, stack)


def _request(payload):
    reader = Reader(payload)
    uid, text = reader.scalar('Q'), reader.text(200)
    attachments = reader.scalar('I')
    reader.end()
    if (not 0 < uid < 2**63 or not text.strip() or attachments
            or any(char in text for char in '<>') or '#c' in text.casefold()):
        raise ValueError('Invalid plain megaphone message')
    return uid, text


def _ack(changes=(), result=0):
    from els_server.protocol.inventory_management_messages import seal_ack

    return Event(0x201, kind=0x243, payload=seal_ack(changes, result))


def _consume(path, owner, account, payload, operation, guard):
    from els_server.storage.equipment_receipt_state import current_changes
    from els_server.storage.inventory_actions import _commit, _identity, _previous
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.item_instances import reduce_count, remove
    from els_server.storage.profession_state import require_owner

    uid, text = _request(payload)
    _, digest = _identity(owner, 0x242, payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        guard()
        require_active_character(db, owner)
        require_owner(db, owner, account)
        previous = _previous(db, operation, digest)
        before = load_items(db, owner)
        if previous is not None:
            response = _ack(current_changes(db, operation, owner, 0x242, previous, before))
            encode_event(response)
            guard()
            return response, None
        item = next((item for item in before if item['uid'] == uid), None)
        if item is None or item['template'] not in TEMPLATES or item['group'] != 4:
            raise ValueError('Megaphone requires an owned original item')
        require_current(item)
        require_unlocked(item)
        position = item['group'], item['slot']
        if item['count'] == 1:
            remove(db, owner, item)
            remaining = None
        else:
            remaining = reduce_count(item, item['count'] - 1)
            db.execute('UPDATE inventory_items SET count=? WHERE owner=? AND uid=?',
                       (remaining['count'], owner, uid))
        after = load_items(db, owner)
        response = _ack(((position, remaining),))
        event = announcement(character_name(db, owner), text, channel=1, account=account, actor=owner)
        encode_event(response)
        encode_event(event)
        _commit(db, operation, digest, owner, 0x242, [position], before, after)
        guard()
        return response, event


def handle(session, event, sequence):
    from els_server.domain.equipment_engrave_flow import current_lease

    actor = session.account
    store = actor.store
    lease = session.shop_session_id
    owner, account = actor.uid, actor.account_id

    def guard():
        if (not ready(session) or not session.application.registry.enabled(account)
                or not current_lease(session)
                or session.account is not actor or actor.store is not store
                or session.shop_session_id != lease or actor.uid != owner
                or store is None or store.uid != owner):
            raise ValueError('Megaphone actor lease changed')

    try:
        if (type(sequence) is not int or not 1 <= sequence < 2**32
                or event.performers not in ((), (0,)) or event.payload_mode != 0
                or event.uid != 2**64-1 or event.target_uid != 2**64-1):
            raise ValueError('Megaphone request envelope')
        guard()
        response, outgoing = _consume(store.path, owner, account, event.payload,
                                      f'{lease}:{owner}:megaphone:{sequence}', guard)
    except (ValueError, sqlite3.Error):
        return [_ack(result=21)]
    # The small horn reaches the current channel. The large horn reaches the
    # deployment. This deployment exposes one channel and one playing registry.
    if outgoing is not None:
        publish(session, (outgoing,))
    return [response]
