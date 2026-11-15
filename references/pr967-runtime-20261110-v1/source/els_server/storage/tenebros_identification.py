"""One owned scroll and three shadow options in one real SQLite transaction.

Probability and scroll preference are the user's explicit local policy. Native
option IDs/tiers are supplied by the shared exact-source Tenebros rules. No ED,
new schema, acquisition channel, reroll or client-side effect is introduced.
"""
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from els_server.domain.tenebros_rules import template_info, draw_initial, validate
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.domain.inventory_items import validate_item
from els_server.game_data import client_data
from els_server.protocol.tenebros_identification_messages import request, acknowledgement
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.equipment_options import replace
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances


SCROLLS = {
    118258: '0596e9f72559e364e14a560addfb6fe1dfce2802878340480eb87c5355c33639',
    118259: '088680b9a897325b65ad55f0259ca0e2ca689089235e822c4e97fd2ac2da8360',
    118260: 'bc200052e1e10a716163943c12d320283d9bfe7b6e331733773e39d96dc515b6',
    118261: 'dbeb78e28e3fe0d79089edfcf85bf735bca33b8f6e3c8798ae1fdf82c70be006',
    118323: '76640c1359d45367b003e022c98b78c778f895f9dda7d8b5567bb82d99df0096',
}


def target_info(target):
    if (target is None or target['group'] != 1 or target['count'] != 1
            or target.get('sealed') or target.get('identified') is False
            or target.get('enhancement', 0) < 0):
        raise ValueError('Owned bag Tenebros initial identification target required')
    from els_server.domain.boosting_gear_identification import require_complete
    require_complete(target)
    info = template_info(target['template'])
    if target.get('option_groups', {}).get('25', []):
        raise ValueError('Existing shadow effects cannot be re-identified')
    return info


def scroll(item):
    if (item is None or item['template'] not in SCROLLS or item['group'] != 4
            or item['metadata'] != 2 or type(item['count']) is not int or item['count'] < 1
            or item.get('sealed') or item.get('identified') is False):
        raise ValueError('Owned exact identification scroll required')
    if hashlib.sha256(client_data().item(item['template'])['record']).hexdigest() != SCROLLS[item['template']]:
        raise ValueError('Tenebros identification material source changed')
    return item


def select_scroll(items, *, now):
    eligible = []
    for item in items:
        if item['template'] not in SCROLLS:
            continue
        try:
            scroll(item)
            require_current(item, now=now)
            require_unlocked(item, now=now)
        except ValueError:
            continue
        eligible.append(item)
    if not eligible:
        raise ValueError('No eligible owned identification scroll')
    # All ordinary variants have the same priority; permanent items follow
    # dated items. UID resolves only otherwise equal authorized priorities.
    return min(eligible, key=lambda i: (i['template'] == 118323,
               i.get('expires_at', float('inf')), i['uid']))


def image(items, target_uid, scroll_uid, options):
    owned = {i['uid']: dict(i) for i in items}
    if len(owned) != len(items):
        raise ValueError('Duplicate identification instance identity')
    target = owned.get(target_uid)
    material = scroll(owned.get(scroll_uid))
    target_info(target)
    values = validate(target['template'], options)
    if target_uid == scroll_uid:
        raise ValueError('Identification target equals material')
    owned[target_uid] = {**target, 'option_groups': {**target.get('option_groups', {}), '25': values}}
    if material['count'] == 1:
        del owned[scroll_uid]
    else:
        owned[scroll_uid] = {**material, 'count': material['count'] - 1}
    return owned


def receipt(db, operation, owner, target_uid, positions):
    row = db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts '
                     'WHERE operation_id=?', (operation,)).fetchone()
    if row is None or row[:2] != (owner, 0x9ef):
        raise ValueError('Tenebros identification receipt owner/kind')
    try:
        before, after = (json.loads(raw) for raw in row[2:])
        if (not isinstance(before, list) or not isinstance(after, list)
                or any(not isinstance(i, dict) for i in before + after)):
            raise ValueError('Tenebros identification receipt arrays')
        before = [validate_item(i) for i in before]
        after = [validate_item(i) for i in after]
        old = {i['uid']: i for i in before}
        new = {i['uid']: i for i in after}
        if len(old) != len(before) or len(new) != len(after) or len(positions) != 2:
            raise ValueError('Tenebros identification receipt instances')
        target = old[target_uid]
        if positions[0] != (target['group'], target['slot']):
            raise ValueError('Tenebros identification receipt target slot')
        materials = [i for i in before if (i['group'], i['slot']) == positions[1]]
        if len(materials) != 1:
            raise ValueError('Tenebros identification receipt material slot')
        material_uid = materials[0]['uid']
        options = new[target_uid]['option_groups']['25']
        if new != image(before, target_uid, material_uid, options):
            raise ValueError('Tenebros identification receipt exact one-scroll effect')
        return material_uid
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('Tenebros identification receipt history') from exc


def current_changes(items, positions, target_uid, material_uid):
    target = next((i for i in items if i['uid'] == target_uid), None)
    if target is None or target['group'] != 1:
        raise ValueError('Tenebros replay target no longer in owned bag')
    points = list(positions)
    for item in items:
        if item['uid'] in (target_uid, material_uid):
            point = (item['group'], item['slot'])
            if point not in points:
                points.append(point)
    current = {(i['group'], i['slot']): i for i in items}
    return [(point, current.get(point)) for point in points]


def perform(path, owner, account_id, payload, operation, *, prepare,
            encode=acknowledgement, randbelow=secrets.randbelow, clock=time.time):
    if not all(callable(f) for f in (prepare, encode, randbelow, clock)):
        raise ValueError('Tenebros identification transaction context')
    target_uid = request(payload)
    owner, digest = _identity(owner, 0x9ef, payload, operation)
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        def guard():
            if Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve() != path:
                raise ValueError('Tenebros identification database authority')
            prepare(db)
            require_active_character(db, owner)
            require_owner(db, owner, account_id)
        guard()
        try:
            old = _previous(db, operation, digest)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError('Tenebros identification receipt positions') from exc
        before = load_items(db, owner)
        wallet = balances(db, owner)
        if old is not None:
            material_uid = receipt(db, operation, owner, target_uid, old)
            reply = encode(current_changes(before, old, target_uid, material_uid))
            encode_event(reply)
            guard()
            return [reply]
        owned = {i['uid']: i for i in before}
        target = owned.get(target_uid)
        info = target_info(target)
        now = int(clock())
        if now < 0:
            raise ValueError('Tenebros identification clock')
        require_current(target, now=now)
        require_unlocked(target, now=now)
        material = select_scroll(before, now=now)
        material_uid = material['uid']
        options = [draw_initial(target['template'], line,
                   randbelow(len(info['types'][line])), randbelow(55),
                   blessed=material['template'] == 118323) for line in range(3)]
        expected = image(before, target_uid, material_uid, options)
        points = [(i['group'], i['slot']) for i in (target, material)]
        preview = encode(current_changes(list(expected.values()), points, target_uid, material_uid))
        encode_event(preview)
        guard()
        for item in (target, material):
            require_current(item, now=int(clock()))
            require_unlocked(item)
        if material['count'] == 1:
            remove(db, owner, material)
        elif db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',
                        (material_uid, owner, material['count'])).rowcount != 1:
            raise ValueError('Tenebros identification scroll changed')
        replace(db, owner, target_uid, target.get('option_groups', {}), expected[target_uid]['option_groups'])
        after = load_items(db, owner)
        if {i['uid']: i for i in after} != expected or balances(db, owner) != wallet:
            raise ValueError('Tenebros identification exact inventory/wallet effect')
        reply = encode(current_changes(after, points, target_uid, material_uid))
        encode_event(reply)
        guard()
        for item in (target, material):
            require_current(item, now=int(clock()))
        _commit(db, operation, digest, owner, 0x9ef, points, before, after)
        guard()
        return [reply]
