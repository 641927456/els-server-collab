"""Character-owned bag positions; pins survive emptying or moving an item."""
import sqlite3
from contextlib import closing
from els_server.protocol import inventory_sort_pin_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.bag_capacity import allowances
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.item_actor import require_active_character
from els_server.storage.erp_support_quest_scope import exists


def snapshot(db, owner):
    if not exists(db, 'inventory_sort_pins'):
        return {}
    pins = {}
    for group, slot in db.execute(
            'SELECT bag_group,slot FROM inventory_sort_pins WHERE owner=? ORDER BY bag_group,slot', (owner,)):
        pins.setdefault(group, []).append(slot)
    return pins


def change(path, owner, payload, operation):
    action, group, slot = wire.request(payload)
    owner, digest = _identity(owner, 0xb37, payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        require_active_character(db, owner)
        old = _previous(db, operation, digest)
        if old is None:
            if slot >= allowances(db, owner)[group]:
                raise ValueError('Unowned sort pin position')
            db.execute('''CREATE TABLE IF NOT EXISTS inventory_sort_pins (
                owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
                bag_group INTEGER NOT NULL CHECK(bag_group IN (1,2,3,4,5,6,7,21,27)),
                slot INTEGER NOT NULL CHECK(slot>=0), PRIMARY KEY(owner,bag_group,slot))''')
            if action == 1:
                db.execute('INSERT OR IGNORE INTO inventory_sort_pins VALUES (?,?,?)', (owner, group, slot))
            else:
                db.execute('DELETE FROM inventory_sort_pins WHERE owner=? AND bag_group=? AND slot=?', (owner, group, slot))
        reply = wire.acknowledgement(snapshot(db, owner), action, group, slot)
        encode_event(reply)
        if old is None:
            # No item is moved, consumed, created or economically modified.
            _commit(db, operation, digest, owner, 0xb37, [(group, slot)], [], [])
        return reply
