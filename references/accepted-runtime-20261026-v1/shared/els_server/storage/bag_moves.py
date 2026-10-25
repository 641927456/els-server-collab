"""Native 104/105 moves inside owned material, special and consumable bags.

The existing move reader applies absolute records for both affected positions.
Stacking uses the same complete-instance key as inventory sorting, up to the
registered stack limit. Retained UIDs never leave their inventory rows.
"""
from els_server.storage.item_actor import require_active_character
import json
import sqlite3
import struct
from contextlib import closing

from els_server.domain.bag_capacity import wire_limit
from els_server.domain.fashion_state import move_ack
from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS, validate_item
from els_server.domain.item_expiration import require_current
from els_server.storage.bag_capacity import allowances
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove


def positions(payload):
    if not isinstance(payload, bytes) or len(payload) != 11:
        raise ValueError('Bag move request length')
    sg, ss, dg, ds, flag = struct.unpack('>BiBiB', payload)
    if sg != dg or sg not in (2, 3, 4, 5, 6, 21) or flag or ss == ds:
        raise ValueError('Unsupported bag move')
    if not all(0 <= slot < wire_limit(sg) for slot in (ss, ds)):
        raise ValueError('Bag move slot')
    return (sg, ss), (dg, ds)


def move_bag_items(path, payload, uid=1001):
    uid = character_uid(uid)
    source, destination = positions(payload)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE');require_active_character(db,uid)
        limit = allowances(db, uid)[source[0]]
        if source[1] >= limit or destination[1] >= limit:
            raise ValueError('Unowned bag bag position')
        items = load_items(db, uid)
        by_position = {(i['group'], i['slot']): i for i in items}
        first, second = by_position.get(source), by_position.get(destination)
        if first is None:
            raise ValueError('Bag source empty')
        for item in (first, second):
            if item is not None:
                require_current(item)
        def stack_state(item):
            return {k: v for k, v in item.items() if k not in ('uid', 'slot', 'count')}
        from els_server.domain.cartridge_selection_box import BOX,relocate_existing_box
        same_stack = first['template']!=BOX and second is not None and stack_state(first) == stack_state(second)
        if same_stack:
            delta = min(first['count'], TEMPLATE_MAX_STACKS[first['template']] - second['count'])
            if delta == 0:
                return move_ack([(source, first), (destination, second)])
            remaining = dict(first, count=first['count'] - delta) if delta < first['count'] else None
            moved = dict(second, count=second['count'] + delta)
        else:
            remaining = dict(second, group=source[0], slot=source[1]) if second else None
            moved = dict(first, group=destination[0], slot=destination[1])
        if first['template']==BOX:moved=relocate_existing_box(first,moved)
        if second is not None and second['template']==BOX and remaining is not None:
            remaining=relocate_existing_box(second,remaining)
        changes = [(source, remaining), (destination, moved)]
        for _, item in changes:
            if item is not None:
                validate_item(item)
        response = move_ack(changes)  # An encoder failure precedes all writes.
        expected = {i['uid']: i for i in items}
        retained = {item['uid']: item for _, item in changes if item is not None}
        for old in (first, second):
            if old is not None:
                expected.pop(old['uid'])
                if old['uid'] not in retained:
                    remove(db, uid, old)
                elif db.execute('UPDATE inventory_items SET slot=? WHERE uid=? AND owner=?',
                                (-old['uid'], old['uid'], uid)).rowcount != 1:
                    raise ValueError('Bag move source owner mismatch')
        for item in retained.values():
            expected[item['uid']] = item
            if db.execute('UPDATE inventory_items SET count=?,slot=? WHERE uid=? AND owner=?',
                          (item['count'], item['slot'], item['uid'], uid)).rowcount != 1:
                raise ValueError('Bag move retained owner mismatch')
        if {i['uid']: i for i in load_items(db, uid)} != expected:
            raise ValueError('Bag move changed unrelated inventory data')
        db.execute('''CREATE TABLE IF NOT EXISTS bag_moves (
            id INTEGER PRIMARY KEY, owner INTEGER NOT NULL, request BLOB NOT NULL,
            before_json TEXT NOT NULL, after_json TEXT NOT NULL)''')
        db.execute('INSERT INTO bag_moves(owner,request,before_json,after_json) VALUES (?,?,?,?)',
                   (uid, payload, json.dumps([first, second], sort_keys=True),
                    json.dumps([remaining, moved], sort_keys=True)))
        return response
