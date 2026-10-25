"""Atomic effect extraction and paid pending imbue; independent of capacity policy.

Character ownership, 10..1 value weights and paid-pending cancellation are explicit
2026-10-24 user policy. Known prices/materials are native config data.
"""
from contextlib import closing
import json, secrets, sqlite3, struct, time
from pathlib import Path
from els_server.protocol import tenebros_storage_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.tenebros_capacity import guard, read as capacity
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_state import load_items
from els_server.storage.npc_trade import balances, charge

OWNERSHIP = 'character'
VALUE_WEIGHTS = (10, 9, 8, 7, 6, 5, 4, 3, 2, 1)
CANCEL_POLICY = 'discard-paid-pending'
POLICY_SHA256 = 'e3cccd4817ce9152edfcf74e552c074516d526dda0bf68e400e75d000c30e76b'

SCHEMAS = {
 'tenebros_effect_storage': 'CREATE TABLE tenebros_effect_storage (owner_id INTEGER NOT NULL CHECK(owner_id>=1), part INTEGER NOT NULL CHECK(part BETWEEN 0 AND 3), slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 5), type_id INTEGER NOT NULL CHECK(type_id>=0), revision INTEGER NOT NULL CHECK(revision>=1), PRIMARY KEY(owner_id,part,slot))',
 'tenebros_effect_pending': 'CREATE TABLE tenebros_effect_pending (owner INTEGER PRIMARY KEY CHECK(owner>=1001), account_id INTEGER NOT NULL CHECK(account_id>=1), session_key TEXT NOT NULL, operation TEXT NOT NULL UNIQUE, item_uid INTEGER NOT NULL CHECK(item_uid>=1), part INTEGER NOT NULL CHECK(part BETWEEN 0 AND 3), line INTEGER NOT NULL CHECK(line BETWEEN 0 AND 2), type_id INTEGER NOT NULL CHECK(type_id>0), candidate INTEGER NOT NULL CHECK(candidate>0), item_json TEXT NOT NULL, state INTEGER NOT NULL CHECK(state BETWEEN 0 AND 2))',
 'tenebros_effect_operations': 'CREATE TABLE tenebros_effect_operations (operation TEXT PRIMARY KEY, digest TEXT NOT NULL, owner INTEGER NOT NULL CHECK(owner>=1001), account_id INTEGER NOT NULL CHECK(account_id>=1), kind INTEGER NOT NULL, details_json TEXT NOT NULL)',
}


def policy_ready():
    if OWNERSHIP not in ('character', 'account') or CANCEL_POLICY != 'discard-paid-pending':
        raise ValueError('Tenebros storage ownership/cancel policy unresolved')
    if type(VALUE_WEIGHTS) is not tuple or len(VALUE_WEIGHTS) != 10 or any(type(w) is not int or w < 0 for w in VALUE_WEIGHTS) or not 0 < sum(VALUE_WEIGHTS) < 2**31:
        raise ValueError('Tenebros stored-effect value weights unresolved')


def key(owner, account_id):
    policy_ready()
    return owner if OWNERSHIP == 'character' else account_id


def schema(db, *, create=False):
    found = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name IN (?,?,?)", tuple(SCHEMAS)))
    if found and found != SCHEMAS:
        raise ValueError('Tenebros storage incompatible schema')
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name IN (?,?,?)", tuple(SCHEMAS)).fetchone():
        raise ValueError('Tenebros storage unexpected trigger')
    if not found and create:
        if not db.in_transaction:
            raise ValueError('Tenebros storage schema outside transaction')
        for sql in SCHEMAS.values():
            db.execute(sql)
    return bool(found) or create


def cells(db, owner, account_id, extras):
    result = [[0]*6 for _ in range(4)]
    if schema(db):
        from els_server.domain.tenebros_rules import type_options
        for part, slot, type_id, revision in db.execute('SELECT part,slot,type_id,revision FROM tenebros_effect_storage WHERE owner_id=?', (key(owner, account_id),)):
            wire.integer(part, 0, 3); wire.integer(slot, 0, 5); wire.integer(revision, 1, 2**63-1)
            if type_id:
                # SQL retains the type, never the extracted magnitude. Native UI
                # reads an option ID and resolves its type and line through maps.
                values = type_options(type_id)
                if len(values) != 10:
                    raise ValueError('Tenebros stored effect type')
                result[part][slot] = values[0]
    for part in range(4):
        wire.storage_row(extras[part], result[part])
    return result


def target(item, part, *, save=False, now):
    from els_server.domain.tenebros_rules import template_info, validate
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    if item is None or item['group'] != 1 or item['count'] != 1 or item.get('sealed') or item.get('identified') is False or item.get('enhancement', 0) < 0:
        raise ValueError('Tenebros owned identified bag equipment')
    if template_info(item['template'])['part'] != part:
        raise ValueError('Tenebros equipment part mismatch')
    require_current(item, now=now); require_unlocked(item, now=now)
    validate(item['template'], item.get('option_groups', {}).get('25', []))
    if save and (item.get('enhancement', 0) >= 9 or item.get('reforge', [0])[0] >= 12):
        raise ValueError('Tenebros native save enhancement/reforge limit')
    return item


def quote(probabilities=None):
    from els_server.domain.tenebros_rules import load_quote
    base_ed, base_materials = load_quote()
    delta = 0 if probabilities is None else sum(abs(a-b) for a, b in zip(probabilities, (35, 35, 30)))
    return base_ed+15000*delta, {template: count+{701000: 50, 118253: 20}.get(template, 0)*delta
                               for template, count in base_materials.items()}


def debit(db, owner, account_id, items, demand, *, now):
    from els_server.domain.manufacture_requirements import inventory_candidates
    from els_server.storage.manufacture_debits import apply_debits
    candidates = inventory_candidates(items, now=now)
    allocation = []
    for template, amount in demand.items():
        remaining = amount
        for uid, count in sorted(candidates.get(template, ())):
            quantity = min(remaining, count)
            if quantity:
                allocation.append(dict(uid=uid, quantity=quantity)); remaining -= quantity
            if not remaining:
                break
        if remaining:
            raise ValueError('Tenebros native material demand')
    changes = apply_debits(db, owner, account_id, demand, allocation, now=now)
    return changes


def weighted(values, weights, randbelow):
    roll = randbelow(sum(weights))
    wire.integer(roll, 0, sum(weights)-1)
    for value, weight in zip(values, weights):
        if roll < weight:
            return value
        roll -= weight
    raise ValueError('Tenebros weighted draw')


def set_cell(db, storage_owner, part, slot, value):
    row = db.execute('SELECT revision FROM tenebros_effect_storage WHERE owner_id=? AND part=? AND slot=?', (storage_owner, part, slot)).fetchone()
    revision = 1 if row is None else wire.integer(row[0], 1, 2**63-2)+1
    db.execute('INSERT INTO tenebros_effect_storage VALUES(?,?,?,?,?) ON CONFLICT(owner_id,part,slot) DO UPDATE SET type_id=excluded.type_id,revision=excluded.revision',
               (storage_owner, part, slot, value, revision))
    return revision


def stored_rows(db, storage_owner):
    return {(part, slot): (value, revision) for part, slot, value, revision in db.execute(
        'SELECT part,slot,type_id,revision FROM tenebros_effect_storage WHERE owner_id=?', (storage_owner,))}


def pending_row(db, owner):
    return db.execute('SELECT operation,item_uid,part,line,type_id,candidate,item_json,state,session_key,account_id FROM tenebros_effect_pending WHERE owner=?', (owner,)).fetchone()


def current_changes(db, operation, digest, owner, kind, items):
    """This feature's receipt validator; no generic kind whitelist is widened."""
    from els_server.domain.inventory_items import validate_item
    row = db.execute('SELECT request_hash,owner,kind,positions_json,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?', (operation,)).fetchone()
    if row is None or row[:3] != (digest, owner, kind) or kind not in (0x9f4, 0x9f6, 0x9f8, 0x855):
        raise ValueError('Tenebros mismatched inventory receipt')
    positions = json.loads(row[3]); before = json.loads(row[4]); after = json.loads(row[5])
    if type(positions) is not list or type(before) is not list or type(after) is not list:
        raise ValueError('Tenebros stored receipt collections')
    points = []
    for pos in positions:
        if type(pos) is not list or len(pos) != 2:
            raise ValueError('Tenebros receipt position')
        wire.integer(pos[0], 1, 31); wire.integer(pos[1], 0, 32767)
        if tuple(pos) in points:
            raise ValueError('Tenebros duplicate receipt position')
        points.append(tuple(pos))
    snapshots = []
    for rows in (before, after):
        checked = [validate_item(item) for item in rows]
        if len({i['uid'] for i in checked}) != len(checked) or len({(i['group'], i['slot']) for i in checked}) != len(checked):
            raise ValueError('Tenebros duplicate receipt instance')
        snapshots.extend(checked)
    affected = {i['uid'] for i in snapshots if (i['group'], i['slot']) in points}
    current = {(i['group'], i['slot']): i for i in items}
    for item in items:
        pos = (item['group'], item['slot'])
        if item['uid'] in affected and pos not in points:
            points.append(pos)
    return [(pos, current.get(pos)) for pos in points]


def reply(db, owner, account_id, kind, part, changes, *, candidate=0, result=0):
    current = capacity(db, account_id)
    options = cells(db, owner, account_id, current['extras'])
    ed = balances(db, owner)['ed']
    if kind == 0x9f4:
        return wire.save_ack(ed, current['extras'][part], options[part], changes, result=result)
    if kind == 0x9f6:
        return wire.load_ack(ed, candidate, current['extras'][part], options[part], changes, result=result)
    return wire.confirm_ack(changes=changes, result=result)


def paid_pending(db, owner, account_id, pending):
    operation, uid, part, line, type_id, candidate, original, status, session_key, stored_account = pending
    record = db.execute('SELECT digest,owner,account_id,kind,details_json FROM tenebros_effect_operations WHERE operation=?', (operation,)).fetchone()
    if record is None or record[1:4] != (owner, account_id, 0x9f6) or stored_account != account_id:
        raise ValueError('Tenebros orphan or foreign paid pending')
    details = json.loads(record[4])
    if type(details) is not dict or set(details) != {'uid', 'part', 'line', 'type_id', 'candidate', 'session_key', 'slot'}:
        raise ValueError('Tenebros malformed paid metadata')
    expected = dict(uid=uid, part=part, line=line, type_id=type_id, candidate=candidate, session_key=session_key, slot=details['slot'])
    if details != expected:
        raise ValueError('Tenebros pending/paid metadata mismatch')
    payload = struct.pack('>QiiiBi', uid, part, line, details['slot'], 0, 0)
    digest = _identity(owner, 0x9f6, struct.pack('>Q', account_id)+session_key.encode()+b'\0'+payload, operation)[1]
    if record[0] != digest or _previous(db, operation, digest) is None:
        raise ValueError('Tenebros unpaid pending request')
    row = db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?', (operation,)).fetchone()
    if row is None or row[:2] != (owner, 0x9f6):
        raise ValueError('Tenebros unpaid pending inventory')
    before = {i['uid']: i for i in json.loads(row[2])}; after = {i['uid']: i for i in json.loads(row[3])}
    if before.get(uid) != json.loads(original) or after.get(uid) != before.get(uid):
        raise ValueError('Tenebros initial load changed its target')
    return details


def perform(path, owner, account_id, kind, payload, operation, session_key, *, prepare, randbelow=None, now=None, encode=encode_event):
    policy_ready()
    randbelow = secrets.randbelow if randbelow is None else randbelow
    parsers = {0x9f4: wire.save_request, 0x9f6: wire.load_request, 0x9f8: wire.confirm_request, 0x855: wire.cancel_request}
    if kind not in parsers:
        raise ValueError('Tenebros storage request kind')
    request = parsers[kind](payload)
    if type(session_key) is not str or not 1 <= len(session_key) <= 160:
        raise ValueError('Tenebros current selected session key')
    owner, digest = _identity(owner, kind, struct.pack('>Q', account_id)+session_key.encode()+b'\0'+payload, operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw', uri=True, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON'); db.execute('BEGIN IMMEDIATE')
        guard(db, owner, account_id, prepare, npc=kind != 0x855)
        clock = int(time.time()) if now is None else wire.integer(now, 0, 2**63-1)
        before = load_items(db, owner); wallet = balances(db, owner)
        expected_items = {i['uid']: i for i in before}; expected_wallet = wallet
        old_capacity = capacity(db, account_id)
        old = _previous(db, operation, digest)
        have_schema = schema(db)
        if old is not None:
            stored = db.execute('SELECT digest,owner,account_id,kind,details_json FROM tenebros_effect_operations WHERE operation=?', (operation,)).fetchone() if have_schema else None
            if stored is None or stored[:4] != (digest, owner, account_id, kind):
                raise ValueError('Tenebros missing/conflicting operation state')
            replayed_changes = current_changes(db, operation, digest, owner, kind, before)
            if kind == 0x855:
                guard(db, owner, account_id, prepare)
                return []
            details = json.loads(stored[4]); candidate = 0; result = 0
            if type(details) is not dict or 'part' not in details:
                raise ValueError('Tenebros malformed operation metadata')
            wire.integer(details['part'], 0, 3)
            if kind == 0x9f6:
                active = db.execute('SELECT operation,item_uid,part,line,type_id,candidate,item_json,state,session_key,account_id FROM tenebros_effect_pending WHERE owner=?', (owner,)).fetchone()
                if active is not None and active[0] == operation and active[7:] == (0, session_key, account_id):
                    paid_pending(db, owner, account_id, active)
                    item = target(next((i for i in before if i['uid'] == active[1]), None), active[2], now=clock)
                    if item != json.loads(active[6]):
                        raise ValueError('Tenebros stale paid pending replay')
                    candidate = active[5]
                else:
                    result = 2005
            response = reply(db, owner, account_id, kind, details['part'], replayed_changes, candidate=candidate, result=result)
            encode(response); guard(db, owner, account_id, prepare, npc=kind != 0x855)
            return [response]
        # No schema appears for malformed/unauthorized requests or read-only sync.
        schema(db, create=True)
        pending = pending_row(db, owner)
        expected_pending = pending
        storage_owner = key(owner, account_id)
        expected_cells = stored_rows(db, storage_owner)
        positions = []; candidate = 0; part = 0
        if kind == 0x855:
            if pending is not None and pending[7:] == (0, session_key, account_id):
                db.execute('UPDATE tenebros_effect_pending SET state=2 WHERE owner=? AND state=0', (owner,))
                expected_pending = (*pending[:7], 2, *pending[8:])
        elif kind == 0x9f8:
            uid = request
            if pending is None or pending[1] != uid or pending[7:] != (0, session_key, account_id):
                raise ValueError('Tenebros confirmation without current paid pending')
            paid_pending(db, owner, account_id, pending)
            _, _, part, line, type_id, candidate, original, _, _, _ = pending
            item = target(next((i for i in before if i['uid'] == uid), None), part, now=clock)
            if item != json.loads(original):
                raise ValueError('Tenebros pending target instance changed')
            from els_server.domain.tenebros_rules import option_info, validate
            info = option_info(candidate)
            if info['slot'] != line or info['type_id'] != type_id:
                raise ValueError('Tenebros pending candidate type/line changed')
            groups = item.get('option_groups', {}); values = list(groups['25']); values[line] = candidate
            updated = {**groups, '25': validate(item['template'], values)}
            from els_server.storage.equipment_options import replace
            replace(db, owner, uid, groups, updated)
            expected_items[uid] = {**item, 'option_groups': updated}
            db.execute('UPDATE tenebros_effect_pending SET state=1 WHERE owner=? AND state=0', (owner,))
            expected_pending = (*pending[:7], 1, *pending[8:])
            positions = [(item['group'], item['slot'])]
        else:
            if pending is not None and pending[7] == 0:
                if pending[8:] == (session_key, account_id):
                    raise ValueError('Tenebros another paid pending is active')
                # Old selected sessions can never confirm a cold-login pending.
                db.execute('UPDATE tenebros_effect_pending SET state=2 WHERE owner=? AND state=0', (owner,))
                expected_pending = (*pending[:7], 2, *pending[8:])
            uid, part = request[:2]
            slot = request[2] if kind == 0x9f4 else request[3]
            extra = capacity(db, account_id)['extras'][part]
            if slot >= 3+extra:
                raise ValueError('Tenebros storage slot not unlocked')
            item = target(next((i for i in before if i['uid'] == uid), None), part, save=kind == 0x9f4, now=clock)
            from els_server.domain.tenebros_rules import option_info, type_options, validate
            fee, materials = quote(request[3] if kind == 0x9f4 else None)
            if wallet['ed'] < fee or wallet['revision'] >= 2**63-1:
                raise ValueError('Tenebros insufficient ED/revision')
            if kind == 0x9f4:
                line = weighted((0, 1, 2), request[3], randbelow)
                type_id = option_info(item['option_groups']['25'][line])['type_id']
            else:
                line = request[2]
                saved = db.execute('SELECT type_id FROM tenebros_effect_storage WHERE owner_id=? AND part=? AND slot=?', (storage_owner, part, slot)).fetchone()
                if saved is None or not saved[0]:
                    raise ValueError('Tenebros empty stored effect')
                type_id = saved[0]; values = type_options(type_id)
                if len(values) != 10 or option_info(values[0])['slot'] != line:
                    raise ValueError('Tenebros stored effect line')
                from els_server.domain.tenebros_rules import draw_type
                candidate = draw_type(item['template'], line, type_id, randbelow(sum(VALUE_WEIGHTS)))
                proposed = list(item['option_groups']['25']); proposed[line] = candidate
                validate(item['template'], proposed)
            material_changes = debit(db, owner, account_id, before, materials, now=clock)
            positions = [(r['before']['group'], r['before']['slot']) for r in material_changes]
            for change in material_changes:
                if change['after'] is None:
                    expected_items.pop(change['before']['uid'])
                else:
                    expected_items[change['before']['uid']] = change['after']
            charge(db, owner, wallet, fee)
            expected_wallet = {**wallet, 'ed': wallet['ed']-fee, 'revision': wallet['revision']+1}
            if kind == 0x9f4:
                from els_server.storage.item_instances import remove
                remove(db, owner, item)
                expected_items.pop(uid)
                positions.append((item['group'], item['slot']))
                revision = set_cell(db, storage_owner, part, slot, type_id)
                expected_cells[(part, slot)] = (type_id, revision)
            else:
                revision = set_cell(db, storage_owner, part, slot, 0)
                expected_cells[(part, slot)] = (0, revision)
                db.execute('INSERT INTO tenebros_effect_pending VALUES(?,?,?,?,?,?,?,?,?,?,0) ON CONFLICT(owner) DO UPDATE SET account_id=excluded.account_id,session_key=excluded.session_key,operation=excluded.operation,item_uid=excluded.item_uid,part=excluded.part,line=excluded.line,type_id=excluded.type_id,candidate=excluded.candidate,item_json=excluded.item_json,state=0',
                    (owner, account_id, session_key, operation, uid, part, line, type_id, candidate, json.dumps(item, sort_keys=True)))
                expected_pending = (operation, uid, part, line, type_id, candidate, json.dumps(item, sort_keys=True), 0, session_key, account_id)
        after = load_items(db, owner)
        if ({i['uid']: i for i in after} != expected_items or balances(db, owner) != expected_wallet
                or capacity(db, account_id) != old_capacity):
            raise ValueError('Tenebros exact inventory/balance/capacity transition')
        points = sorted(set(positions)); current = {(i['group'], i['slot']): i for i in after}
        changes = [(pos, current.get(pos)) for pos in points]
        response = None if kind == 0x855 else reply(db, owner, account_id, kind, part, changes, candidate=candidate)
        if response is not None:
            encode(response)
        guard(db, owner, account_id, prepare, npc=kind != 0x855)
        _commit(db, operation, digest, owner, kind, points, before, after)
        details = dict(part=part, candidate=candidate)
        if kind == 0x9f6:
            details.update(uid=uid, line=line, type_id=type_id, session_key=session_key, slot=slot)
        db.execute('INSERT INTO tenebros_effect_operations VALUES(?,?,?,?,?,?)', (operation, digest, owner, account_id, kind, json.dumps(details)))
        # Receipt writes are part of the transaction. Validate their state and
        # the captured actor after those final writes, before committing.
        guard(db, owner, account_id, prepare, npc=kind != 0x855)
        if (stored_rows(db, storage_owner) != expected_cells or pending_row(db, owner) != expected_pending
                or {i['uid']: i for i in load_items(db, owner)} != expected_items
                or balances(db, owner) != expected_wallet or capacity(db, account_id) != old_capacity):
            raise ValueError('Tenebros final persistent transition')
        stored = db.execute('SELECT digest,owner,account_id,kind,details_json FROM tenebros_effect_operations WHERE operation=?', (operation,)).fetchone()
        if stored is None or stored[:4] != (digest, owner, account_id, kind) or json.loads(stored[4]) != details:
            raise ValueError('Tenebros final operation receipt')
        current_changes(db, operation, digest, owner, kind, after)
        cells(db, owner, account_id, old_capacity['extras'])
        return [] if response is None else [response]


def snapshot(path, owner, account_id, *, prepare):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=10)) as db:
        db.execute('BEGIN'); guard(db, owner, account_id, prepare)
        current = capacity(db, account_id)
        options = cells(db, owner, account_id, current['extras'])
        guard(db, owner, account_id, prepare)
        return dict(extras=current['extras'], options=options)


def abandon(path, owner, account_id, session_key):
    """Server-captured lease cleanup only: discard a paid candidate, refund nothing.

    A disconnected actor cannot satisfy the live lease guard. This helper has no
    request route and can only close the exact previously captured owner/session.
    A subsequent selected session also discards the old pending before a new load.
    """
    from els_server.storage.profession_state import require_owner
    wire.integer(owner, 1001, 2**63-1); wire.integer(account_id, 1, 2**63-1)
    if type(session_key) is not str or not 1 <= len(session_key) <= 160:
        raise ValueError('Tenebros cleanup selected session')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw', uri=True, timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE'); require_owner(db, owner, account_id)
        if not schema(db):
            return False
        return bool(db.execute('UPDATE tenebros_effect_pending SET state=2 WHERE owner=? AND account_id=? AND session_key=? AND state=0',
                               (owner, account_id, session_key)).rowcount)
