"""File avatar pieces on the page their own template belongs to.

Bag7 is the ordinary avatar tab and bag27 the cash/ice one; the template's
flags8&256 decides which, the same rule the client uses to pick a tab. Older
move code and older saves left pieces on the sibling page, where the client
paints them under a tab it would never file them in.

The read path tolerates that drift (a refused row made the whole inventory
unloadable), so this repair is the only thing that puts them back. It runs next
to equipment_circuits.repair_missing - after inventory initialization and
before the login/refresh snapshot - so the client always receives a canonical
layout, and it is a no-op once a save is clean.
"""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from els_server.domain.bag_capacity import wire_limit
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS
from els_server.storage.sqlite_timing import write_transaction


def misplaced(items, capacity):
    """(item, target_group, target_slot) for every piece on the wrong page."""
    taken = {}
    for item in items:
        taken.setdefault(item['group'], set()).add(item['slot'])
    plans = []
    for item in sorted(items, key=lambda i: i['uid']):
        group = item['group']
        if group not in (7, 27) or item['slot'] < 0:
            continue
        native = TEMPLATE_BAG_GROUPS.get(item['template'])
        if native not in (7, 27) or native == group:
            continue
        # Keep the slot number when the own page has it free, so a drifted piece
        # does not shuffle the rest of the tab around.
        room = range(min(capacity.get(native, 0), wire_limit(native)))
        slot = item['slot'] if item['slot'] in room and item['slot'] not in taken.get(native, ()) else None
        if slot is None:
            slot = next((n for n in room if n not in taken.get(native, ())), None)
        if slot is None:
            continue
        taken.setdefault(native, set()).add(slot)
        taken[group].discard(item['slot'])
        plans.append((item, native, slot))
    return plans


def repair(path, owner):
    """Move drifted avatar pieces to their own page; return the audit records.

    Reads first and only opens a write transaction when the save really holds a
    mis-filed piece, so the login/refresh path stays read-only in the normal
    case.
    """
    from els_server.storage.bag_capacity import allowances
    from els_server.storage.inventory_state import load_items
    from els_server.storage.read_scope import snapshot_connection

    with snapshot_connection(path) as db:
        db.execute('BEGIN')
        items = load_items(db, owner)
        capacity = allowances(db, owner)
        db.commit()
    plans = misplaced(items, capacity)
    if not plans:
        return []
    audit = []
    uri = Path(path).resolve().as_uri() + '?mode=rw'
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        with write_transaction(db):
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_migrations'").fetchone() is None:
                db.execute('CREATE TABLE inventory_migrations (name TEXT PRIMARY KEY, audit_json TEXT NOT NULL)')
            for item, group, slot in plans:
                name = 'avatar-page-v1:' + str(item['uid'])
                record = dict(owner=owner, uid=item['uid'], template=item['template'],
                              from_group=item['group'], from_slot=item['slot'],
                              group=group, slot=slot,
                              policy='flags8-256-avatar-page')
                previous = db.execute('SELECT audit_json FROM inventory_migrations WHERE name=?', (name,)).fetchone()
                if previous is not None:
                    if json.loads(previous[0]) != record:
                        raise ValueError('Conflicting avatar page filing evidence')
                    continue
                # The row must still be the one that was planned: a concurrent
                # move between the read and this write leaves it alone.
                changed = db.execute('UPDATE inventory_items SET bag_group=?,slot=? '
                                     'WHERE uid=? AND owner=? AND bag_group=? AND slot=?',
                                     (group, slot, item['uid'], owner, item['group'], item['slot']))
                if changed.rowcount != 1:
                    continue
                db.execute('INSERT INTO inventory_migrations VALUES(?,?)',
                           (name, json.dumps(record, sort_keys=True)))
                audit.append(record)
    return audit
