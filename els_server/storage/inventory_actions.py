"""Transactional UI stack splits/discards with operation receipts.

Receipt retries serialize CURRENT affected slots. They never repeat a decrement,
allocate a second UID, or clear a replacement that moved into a historical slot.
"""
from els_server.storage.item_actor import require_active_character
import hashlib
import json
import sqlite3
from contextlib import closing
from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS, validate_item
from els_server.domain.item_expiration import require_current
from els_server.protocol.inventory_action_messages import (
    split_request, split_ack, discard_request, discard_ack)
from els_server.storage.bag_capacity import allowances
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_expiration import assign, forget


def _identity(uid, kind, payload, operation):
    uid = character_uid(uid)
    if not isinstance(operation, str) or not 1 <= len(operation) <= 160:
        raise ValueError('Inventory action operation identity')
    digest = hashlib.sha256(str(uid).encode() + b':' + str(kind).encode() + b':' + payload).hexdigest()
    return uid, digest


def _previous(db, operation, digest):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone():
        return None
    old = db.execute('SELECT request_hash,positions_json FROM inventory_action_receipts WHERE operation_id=?', (operation,)).fetchone()
    if old is not None:
        if old[0] != digest:
            raise ValueError('Conflicting inventory action retry')
        return [tuple(p) for p in json.loads(old[1])]
    return None


def _commit(db, operation, digest, uid, kind, positions, before, after):
    db.execute('''CREATE TABLE IF NOT EXISTS inventory_action_receipts (
        operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, owner INTEGER NOT NULL,
        kind INTEGER NOT NULL, positions_json TEXT NOT NULL, before_json TEXT NOT NULL,
        after_json TEXT NOT NULL)''')
    db.execute('INSERT INTO inventory_action_receipts VALUES (?,?,?,?,?,?,?)',
               (operation, digest, uid, kind, json.dumps(positions),
                json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True)))


def split_stack(path, uid, payload, operation):
    source, destination, quantity = split_request(payload)
    uid, digest = _identity(uid, 0x555, payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE');require_active_character(db,uid)
        old = _previous(db, operation, digest)
        items = load_items(db, uid)
        by_position = {(i['group'], i['slot']): i for i in items}
        if old is not None:
            return split_ack(current_changes(db,operation,uid,0x555,old,items))
        limit = allowances(db, uid)[source[0]]
        if source[1] >= limit or destination[1] >= limit:
            raise ValueError('Unowned split destination')
        item = by_position.get(source)
        if item is None or destination in by_position:
            raise ValueError('Split needs an owned source and an empty destination')
        require_current(item)
        from els_server.domain.item_locks import require_unlocked
        require_unlocked(item)
        if TEMPLATE_MAX_STACKS[item['template']] <= 1 or quantity > item['count']:
            raise ValueError('Invalid stack split quantity')
        if quantity == item['count']:
            remaining = None
            moved = validate_item(dict(item, slot=destination[1]))
        else:
            next_uid = db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
            if type(next_uid) is not int or not 1 <= next_uid < 2**63 - 1:
                raise ValueError('Split UID sequence bound')
            remaining = validate_item(dict(item, count=item['count'] - quantity))
            moved = validate_item(dict(item, uid=next_uid, count=quantity, slot=destination[1]))
        response = split_ack([(source, remaining), (destination, moved)])
        if remaining is None:
            db.execute('UPDATE inventory_items SET slot=? WHERE uid=? AND owner=?', (destination[1], item['uid'], uid))
        else:
            db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?', (remaining['count'], item['uid'], uid))
            db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',
                       (moved['uid'], uid, moved['template'], moved['metadata'], moved['count'], moved['group'], moved['slot']))
            db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1', (moved['uid'] + 1,))
            if 'expires_at' in moved:
                assign(db, uid, moved['uid'], moved['expires_at'])
        load_items(db, uid)
        _commit(db, operation, digest, uid, 0x555, [source, destination], [item, None], [remaining, moved])
        return response


def discard(path, uid, payload, operation, *, with_updates=False):
    if type(with_updates) is not bool:raise ValueError('Discard response mode')
    item_uid, quantity = discard_request(payload)
    uid, digest = _identity(uid, 0x109, payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE');require_active_character(db,uid)
        old = _previous(db, operation, digest)
        items = load_items(db, uid)
        if old is not None:
            changes=current_changes(db,operation,uid,0x109,old,items)
            position=old[0];response=discard_ack(dict(changes).get(position),position)
            if with_updates:
                from els_server.storage.inventory_management import _updates
                return response,_updates([(p,i) for p,i in changes if p not in old])
            return response
        item = next((i for i in items if i['uid'] == item_uid), None)
        if item is None or item['group'] not in (1, 2, 3, 4, 5, 6, 7, 21, 27):
            raise ValueError('Discard requires an owned bag item')
        require_current(item)
        from els_server.domain.item_locks import require_unlocked
        require_unlocked(item)
        # 2278D70 authorizes a concrete owned UID/count in bag inventory.
        # Do not reuse 2C5EF30's batch-cleanup classification as a general
        # discard permission: it excludes ordinary valid potions/equipment.
        if quantity > item['count']:
            raise ValueError('Discard exceeds owned count')
        remaining = validate_item(dict(item, count=item['count'] - quantity)) if quantity < item['count'] else None
        position = (item['group'], item['slot'])
        response = discard_ack(remaining, position)
        if remaining is not None:
            db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?', (remaining['count'], item_uid, uid))
        else:
            for table in ('equipment_attributes', 'equipment_durability', 'equipment_enhancement', 'equipment_options', 'equipment_identification', 'equipment_enhancement_progress', 'item_seals','artifact_equipment_state','equipment_chip_tuning','equipment_reforge_states','equipment_engrave_previews'):
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    db.execute(f'DELETE FROM {table} WHERE item_uid=?', (item_uid,))
            forget(db, item_uid)
            from els_server.storage.item_locks import forget as forget_lock
            forget_lock(db, item_uid)
            db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?', (item_uid, uid))
        load_items(db, uid)
        _commit(db, operation, digest, uid, 0x109, [position], [item], [remaining])
        return (response,[]) if with_updates else response
