"""Town inventory management transactions, isolated from shop/dungeon code."""
from els_server.storage.item_actor import require_active_character
import json
import sqlite3
import time
from collections import defaultdict
from contextlib import closing
from els_server.domain.fashion_state import move_ack
from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS, FASHION_EQUIP_SLOTS
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import settings, require_unlocked
from els_server.domain.normal_equipment import definitions
from els_server.domain.ordinary_accessories import definitions as accessory_definitions
from els_server.protocol.inventory_management_messages import (
    sort_ack, category_sort_request, category_sort_ack, lock_request, lock_ack)
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_locks import assign, forget
from els_server.storage.reward_state import validate_balances
from els_server.storage.equipment_receipt_state import current_changes

BAGS = (1, 2, 3, 4, 5, 6, 7, 21, 27)


def _updates(changes):
    # Keep each standalone 105 within the framing limit, including dated items.
    return [Event(0x201, kind=0x105, payload=move_ack(changes[n:n+80]))
            for n in range(0, len(changes), 80)]


def _sort_response(items, positions, groups=BAGS, request_kind=0xbd6):
    current = {(i['group'], i['slot']): i for i in items}
    # BD7 also builds the native all-items view (group ST_END=28). A following
    # 105 restores each item's physical bag/slot after that view is ordered.
    ordered = sorted((i for i in items if i['group'] in groups),
                     key=lambda i: (i['group'], i['slot']))
    if request_kind == 0x370:
        return [Event(0x201, kind=0x371, payload=category_sort_ack(groups[0], ordered))]
    response = [Event(0x201, kind=0xbd7, payload=sort_ack(ordered))]
    response += _updates([(p, current.get(p)) for p in positions])
    return response


def sort_inventory(path, owner, payload, operation):
    if payload != b'':
        raise ValueError('Native automatic sort has no request fields')
    return _sort_inventory(path, owner, payload, operation, BAGS, 0xbd6)


def sort_category_inventory(path, owner, payload, operation):
    category = category_sort_request(payload)
    if category not in BAGS:
        raise ValueError('Unsupported owned sort category')
    return _sort_inventory(path, owner, payload, operation, (category,), 0x370)


def _sort_inventory(path, owner, payload, operation, groups, request_kind):
    owner, digest = _identity(owner, request_kind, payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        old = _previous(db, operation, digest)
        before = load_items(db, owner)
        if old is not None:
            return _sort_response(before, old, groups, request_kind)
        bags = defaultdict(list)
        for item in before:
            if item['group'] in groups:
                # Expired items must go through the expiration lifecycle.
                require_current(item)
                bags[item['group']].append(dict(item))
        after = []
        removed = []
        for group in groups:
            targets = {}
            compact = []
            for item in sorted(bags[group], key=lambda i: (i['template'], i['slot'], i['uid'])):
                # Different expiration/instance state never merges.
                key = json.dumps({k: v for k, v in item.items() if k not in ('uid', 'slot', 'count')}, sort_keys=True)
                target = targets.get(key)
                cap = TEMPLATE_MAX_STACKS[item['template']]
                if target and cap > 1:
                    amount = min(cap-target['count'], item['count'])
                    target['count'] += amount
                    item['count'] -= amount
                if item['count']:
                    compact.append(item)
                    targets[key] = item
                else:
                    removed.append(item['uid'])
            for slot, item in enumerate(compact):
                item['slot'] = slot
                after.append(item)
        positions = sorted({(i['group'], i['slot']) for i in before if i['group'] in groups} |
                           {(i['group'], i['slot']) for i in after})
        # Cancel paid previews only when a UID really changes position or leaves.
        # A no-op sort must retain the active preview and its paid receipt.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_engrave_previews'").fetchone():
            retained = {i['uid']: (i['group'], i['slot']) for i in after}
            for old_item in before:
                if old_item['group'] in groups and retained.get(old_item['uid']) != (old_item['group'], old_item['slot']):
                    db.execute('DELETE FROM equipment_engrave_previews WHERE item_uid IN (SELECT uid FROM inventory_items WHERE uid=? AND owner=?)',
                               (old_item['uid'], owner))
        # Move retained UIDs through unique, transaction-local negative slots.
        # DELETE would immediately fire CASCADE children even for deferred FKs.
        # No temporary position is encoded or committed; only consumed stacks
        # leave inventory, via the complete owned-instance removal adapter.
        for item in before:
            if item['group'] in groups:
                if db.execute('UPDATE inventory_items SET slot=? WHERE uid=? AND owner=?',
                              (-item['uid'], item['uid'], owner)).rowcount != 1:
                    raise ValueError('Sort source owner mismatch')
        from els_server.storage.item_instances import remove
        by_uid = {i['uid']: i for i in before}
        for uid in removed:
            remove(db, owner, by_uid[uid])
        for item in after:
            if db.execute('UPDATE inventory_items SET count=?,slot=? WHERE uid=? AND owner=?',
                          (item['count'], item['slot'], item['uid'], owner)).rowcount != 1:
                raise ValueError('Sort retained owner mismatch')
        current = load_items(db, owner)
        expected = {i['uid']: i for i in before if i['group'] not in groups}
        expected.update({i['uid']: i for i in after})
        if {i['uid']: i for i in current} != expected:
            raise ValueError('Sort changed unrelated instance state')
        response = _sort_response(current, positions, groups, request_kind)
        _commit(db, operation, digest, owner, request_kind, positions, before, current)
        return response


def lock_item(path, owner, payload, operation):
    uid, days, action = lock_request(payload)
    owner, digest = _identity(owner, 0x663, payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        old = _previous(db, operation, digest)
        before = load_items(db, owner)
        balance = validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?', (owner,)).fetchone())
        if old is None:
            item = next((i for i in before if i['uid'] == uid), None)
            # The same native instance deadline/663 protocol applies to
            # costumes. Only catalogued wearable instances are admitted here;
            # pet/mount activation items and consumables keep their own paths.
            normal = item is not None and item['template'] in definitions() and item['group'] in (1, 9)
            fashion = item is not None and item['template'] in FASHION_EQUIP_SLOTS and item['group'] in (7, 27, 9)
            accessory = item is not None and item['template'] in accessory_definitions() and item['group'] in (2, 9)
            if item is None or not (normal or fashion or accessory) or item['count'] != 1:
                raise ValueError('Lock requires owned equipment, costume or accessory')
            require_current(item)
            require_unlocked(item)
            maximum, daily = settings()
            now = int(time.time())
            if action == 0:
                if days > maximum or balance['ed'] < days * daily:
                    raise ValueError('Insufficient lock fee')
                assign(db, owner, uid, now + days * 86400)
                db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=?', (days*daily, owner))
            else:
                if 'lock_until' not in item:
                    raise ValueError('Item has no expired lock to clear')
                forget(db, uid)
            positions = [(item['group'], item['slot'])]
            current = load_items(db, owner)
            _commit(db, operation, digest, owner, 0x663, positions, before, current)
        else:
            positions = old
            current = before
        # Replays report today's balances/current item, never historical fees.
        balance = validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?', (owner,)).fetchone())
        by_position = {(i['group'], i['slot']): i for i in current}
        response = [Event(0x201, kind=0x664, payload=lock_ack(balance['ed'], action))]
        response += _updates(current_changes(db,operation,owner,0x663,positions,current)
                             if old is not None else [(p, by_position.get(p)) for p in positions])
        return response
