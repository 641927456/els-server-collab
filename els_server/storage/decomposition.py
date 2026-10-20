"""Atomic ordinary dismantling with current-state replay and no made-up rates."""
import sqlite3
from contextlib import closing
from els_server.domain.decomposition_rules import quote, reward_definition
from els_server.protocol.inventory_management_messages import decompose_request, decompose_ack
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_state import load_items, grant_items
from els_server.storage.inventory_management import _updates
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.protocol.protocol_codec import Event


def decompose(path, owner, payload, operation):
    uids = decompose_request(payload)
    owner, digest = _identity(owner, 0x1c0, payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        old = _previous(db, operation, digest)
        before = load_items(db, owner)
        if old is not None:
            # Retained affected UIDs may have moved since the first result.
            # Refresh current owned instances, never historical rewards or a
            # different item selected by template after an instance is gone.
            changes = current_changes(db, operation, owner, 0x1c0, old, before)
            return ([Event(0x201, kind=0x1c1, payload=decompose_ack())] +
                    _updates(changes))
        by_uid = {i['uid']: i for i in before}
        selected = [by_uid[uid] for uid in uids if uid in by_uid]
        if len(selected) != len(uids):
            raise ValueError('Decomposition requires owned items')
        quotes = [quote(i) for i in selected]
        quantity = sum(q['quantity'] for q in quotes)
        for item in selected:
            remove(db,owner,item)
        reward = reward_definition()
        changed = {}
        remaining = quantity
        while remaining:
            amount = min(99, remaining)
            plan = {k: reward[k] for k in ('template', 'metadata', 'group')}
            for item in grant_items(db, [dict(plan, quantity=amount)], owner):
                changed[item['uid']] = item
            remaining -= amount
        positions = sorted({(i['group'], i['slot']) for i in selected} |
                           {(i['group'], i['slot']) for i in changed.values()})
        after = load_items(db, owner)
        current = {(i['group'], i['slot']): i for i in after}
        changes = [(p, current.get(p)) for p in positions]
        response = [Event(0x201, kind=0x1c1, payload=decompose_ack(changes, {701000: quantity}))]
        _commit(db, operation, digest, owner, 0x1c0, positions, before, after)
        return response
