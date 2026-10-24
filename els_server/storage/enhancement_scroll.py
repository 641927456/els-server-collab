"""Atomic +13 scroll use: one owned scroll, one owned equipment, one receipt."""
import sqlite3
import struct
import time
from contextlib import closing

from els_server.domain.enhancement_scroll import kind, level as scroll_level, scroll
from els_server.protocol.career_messages import use_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_actions import _commit, _identity, _previous
from els_server.storage.inventory_state import load_items


def request(payload):
    if not isinstance(payload, bytes) or len(payload) < 8:
        raise ValueError('Enhancement scroll request width')
    source = struct.unpack_from('>Q', payload)[0]
    target = struct.unpack_from('>Q', payload, 8)[0] if len(payload) >= 16 else 0
    if not 0 < source < 2**63 or not 0 <= target < 2**63:
        raise ValueError('Enhancement scroll request identity')
    return source, target


def candidate(path, owner, payload, operation):
    try:
        source, _ = request(payload)
    except ValueError:
        return False
    with closing(sqlite3.connect(path, timeout=10)) as db:
        row = db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',
                         (owner, source)).fetchone()
        if row is not None and scroll(row[0]):
            return True
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_action_receipts'").fetchone()
                    and db.execute('SELECT 1 FROM inventory_action_receipts WHERE owner=? AND kind=? AND operation_id=?',
                                   (owner, 0x219, operation)).fetchone())


def _target(items, target_uid, scroll_template):
    from els_server.domain.equipment_enhancement import validate
    from els_server.game_data import client_data
    if target_uid:
        item = next((i for i in items if i['uid'] == target_uid), None)
        if item is None or item['group'] not in (1, 9):
            return None
    else:
        wanted = kind(scroll_template)
        candidates = [i for i in items if i['group'] == 9]
        if wanted == 'weapon':
            candidates = [i for i in candidates if client_data().item(i['template'])['equip_position'] == 2]
        elif wanted == 'armor':
            candidates = [i for i in candidates if client_data().item(i['template'])['equip_position'] != 2]
        if len(candidates) != 1:
            return None
        item = candidates[0]
    if item.get('count') != 1 or item.get('sealed'):
        return None
    validate(item['template'], scroll_level(scroll_template))
    return item


def use(path, owner, account_id, payload, operation, now=None):
    source_uid, target_uid = request(payload)
    owner, digest = _identity(owner, 0x219, payload, operation)
    now = int(time.time()) if now is None else now
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    from els_server.storage import equipment_enhancement
    from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS, VERIFIED_TEMPLATES
    from els_server.storage.item_instances import remove
    from els_server.storage.npc_trade import balances
    from els_server.storage.profession_state import require_owner
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        require_owner(db, owner, account_id)
        old = _previous(db, operation, digest)
        items = load_items(db, owner)
        ed = balances(db, owner)['ed']
        if old is not None:
            return [use_ack(current_changes(db, operation, owner, 0x219, old, items), ed=ed)]
        source = next((i for i in items if i['uid'] == source_uid), None)
        if (source is None or not scroll(source['template'])
                or source.get('sealed') or source.get('count', 0) < 1
                or (source['group'], source['metadata']) != (TEMPLATE_BAG_GROUPS[source['template']],
                                                             VERIFIED_TEMPLATES[source['template']])):
            raise ValueError('Owned enhancement scroll required')
        require_current(source, now=now)
        require_unlocked(source, now=now)
        target = _target(items, target_uid, source['template'])
        if target is None:
            raise ValueError('Enhancement target equipment required')
        require_current(target, now=now)
        require_unlocked(target, now=now)
        target_level = scroll_level(source['template'])
        previous = target.get('enhancement', 0)
        if previous >= target_level:
            raise ValueError('Equipment is already +'+str(target_level)+' or above')
        positions = [(source['group'], source['slot']), (target['group'], target['slot'])]
        remaining = dict(source, count=source['count']-1) if source['count'] > 1 else None
        updated = dict(target, enhancement=target_level)
        preflight = [use_ack([((source['group'], source['slot']), remaining),
                              ((target['group'], target['slot']), updated)],
                             source['template'], ed)]
        for event in preflight:
            encode_event(event)
        equipment_enhancement.replace(db, owner, target['uid'], previous, target_level)
        if remaining is None:
            remove(db, owner, source)
        elif db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',
                        (source_uid, owner, source['count'])).rowcount != 1:
            raise ValueError('Enhancement scroll stack changed')
        after_items = load_items(db, owner)
        current = {(i['group'], i['slot']): i for i in after_items}
        events = [use_ack([(p, current.get(p)) for p in positions], source['template'], ed)]
        _commit(db, operation, digest, owner, 0x219, positions,
                [source, target], [current.get(p) for p in positions if current.get(p)])
        return events
