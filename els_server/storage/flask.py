"""Flask economy and weekly gauge ledger in the real owning SQLite transaction."""
from collections import Counter
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import secrets
import sqlite3
import time
from els_server.domain.flask_rules import require_alchemist, quotation, choose, advance, settings
from els_server.protocol.flask_messages import request, acknowledgement, notification
from els_server.protocol.profession_messages import ProfessionState, level_update
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.storage.manufacture import _active_owner, _authorize, operation_identity
from els_server.storage.profession_state import replace
from els_server.storage.inventory_state import load_items, grant_items
from els_server.storage.manufacture_debits import apply_debits
from els_server.storage.reward_state import validate_balances
from els_server.storage.manufacture_quota import window


def exists(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def actor(db, owner, account_id):
    current = _active_owner(db, owner, account_id)
    state = ProfessionState(**current['state'])
    require_alchemist(state)
    row = db.execute('SELECT level FROM characters WHERE uid=?', (owner,)).fetchone()
    place = db.execute('SELECT town FROM location WHERE uid=?', (owner,)).fetchone()
    from els_server.storage.local_state import TOWN_SCENES
    if row is None or row[0] < 40 or place is None or place[0] not in TOWN_SCENES:
        raise ValueError('Flask current character/town eligibility')
    return current, state


def ledger(db, owner, state, now):
    begin, end = window(now, region='CN')
    rows = db.execute('SELECT period_start,used,gauge,pending_level FROM profession_flask_weekly WHERE owner=? ORDER BY period_start DESC LIMIT 1',
                      (owner,)).fetchone() if exists(db, 'profession_flask_weekly') else None
    if rows and rows[0] > begin:
        raise ValueError('Flask trusted clock moved backwards')
    used = rows[1] if rows and rows[0] == begin else 0
    gauge, pending = rows[2:] if rows else (0, 0)
    if (type(used) is not int or not 0 <= used <= 7 or type(gauge) is not int
            or not 0 <= gauge <= 6000000 or type(pending) is not int or not 0 <= pending <= 10
            or bool(pending) and not gauge):
        raise ValueError('Corrupt Flask ledger')
    # Weekly reset clears only the claimed count; earned gauge/pending reward
    # is retained. Its captured reward level survives unrelated crafting XP.
    return dict(period_start=begin, period_end=end, used=used, gauge=gauge, pending_level=pending)


def projected(row, state):
    cap = settings()['caps'][state.level]
    return dict(used=row['used'], gauge=cap if row['pending_level'] else min(row['gauge'], cap))


def save(db, owner, row):
    if not db.in_transaction:
        raise ValueError('Flask ledger requires outer transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS profession_flask_weekly (
        owner INTEGER NOT NULL, period_start INTEGER NOT NULL,
        used INTEGER NOT NULL CHECK(used BETWEEN 0 AND 7),
        gauge INTEGER NOT NULL CHECK(gauge BETWEEN 0 AND 6000000),
        pending_level INTEGER NOT NULL CHECK(pending_level BETWEEN 0 AND 10),
        PRIMARY KEY(owner,period_start))''')
    db.execute('''INSERT INTO profession_flask_weekly VALUES (?,?,?,?,?)
        ON CONFLICT(owner,period_start) DO UPDATE SET used=excluded.used,gauge=excluded.gauge,pending_level=excluded.pending_level''',
               (owner, row['period_start'], row['used'], row['gauge'], row['pending_level']))


def _positions(before, after):
    left = {(i['group'], i['slot']): i for i in before}
    right = {(i['group'], i['slot']): i for i in after}
    return [p for p in sorted(left.keys() | right.keys()) if left.get(p) != right.get(p)]


def _retry_changes(old, items):
    points = [tuple(p) for p in json.loads(old[3])]
    before, after = json.loads(old[4]), json.loads(old[5])
    affected = {i['uid'] for i in before+after if (i['group'], i['slot']) in points}
    points = list(dict.fromkeys(points + [(i['group'], i['slot']) for i in items if i['uid'] in affected]))
    current = {(i['group'], i['slot']): i for i in items}
    return [(p, current.get(p)) for p in points]


def _prepare(events, authorize, prepare):
    _authorize(authorize)
    if prepare is not None:
        events = prepare(events)
    for event in events:
        encode_event(event)
    _authorize(authorize)
    return events


def execute(path, owner, account_id, kind, payload, operation, *, now=None,
            randbelow=secrets.randbelow, authorize=None, prepare=None, prepare_replay=None):
    operation_identity(operation)
    if kind not in (0x707, 0x9ae):
        raise ValueError('Flask action kind')
    uids = request(payload) if kind == 0x707 else ()
    if kind == 0x9ae and payload != b'':
        raise ValueError('Flask gauge claim must be empty')
    if now is None:
        now = lambda: int(time.time())
    clock = now if callable(now) else lambda: now
    digest = hashlib.sha256(f'{owner}:{account_id}:{kind}:'.encode()+payload).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw', uri=True, timeout=10)) as db:
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            _authorize(authorize)
            stamp = clock()  # after acquiring the real writer lock
            current, state = actor(db, owner, account_id)
            row = ledger(db, owner, state, stamp)
            items = load_items(db, owner)
            balances = validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?', (owner,)).fetchone())
            old = db.execute('SELECT request_hash,owner,kind,positions_json,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',
                             (operation,)).fetchone() if exists(db, 'inventory_action_receipts') else None
            if old:
                if old[:3] != (digest, owner, kind):
                    raise ValueError('Conflicting Flask retry')
                wire = acknowledgement(kind, ed=balances['ed'], state=projected(row, state), changes=_retry_changes(old, items))
                events = [Event(0x201, kind=0x708 if kind == 0x707 else 0x9af, payload=wire),
                          Event(0x201, kind=0x9b0, payload=notification(projected(row, state)))]
                # Existing full-sync repair may acquire another SQLite writer.
                # Retry has no economic write; release writer before legacy sync.
                db.rollback()
                return dict(replayed=True, events=_prepare(events, authorize, prepare_replay), xp=0, rewards={})
            rewards, xp, leveled, next_state = {}, 0, False, state
            quote = None
            ed = balances['ed']
            if kind == 0x707:
                if row['pending_level']:
                    raise ValueError('Claim earned Flask gauge reward first')
                quote = quotation(items, uids, now=stamp)
                for uid in uids:
                    from els_server.domain.cartridge_registration_rules import require_unbound
                    require_unbound(db, uid)
                if ed < quote['fee'] or balances['revision'] >= 2**63-1:
                    raise ValueError('Flask ED insufficient/bound')
                rewards = choose(quote['tier'], randbelow)
                next_state, xp, leveled = advance(state, quote['xp'])
                demand = Counter(next(i['template'] for i in items if i['uid'] == uid) for uid in uids)
                apply_debits(db, owner, account_id, dict(demand), [dict(uid=uid, quantity=1) for uid in uids], now=stamp)
                ed -= quote['fee']
                if db.execute('UPDATE reward_balances SET ed=?,revision=revision+1 WHERE uid=? AND revision=?',
                              (ed, owner, balances['revision'])).rowcount != 1:
                    raise ValueError('Flask stale wallet')
                if row['used'] < 7:
                    cap = settings()['caps'][next_state.level]
                    row['gauge'] = min(cap, row['gauge'] + quote['resale'])
                    if row['gauge'] == cap:
                        row['pending_level'] = next_state.level
                replace(db, owner, account_id, current['revision'], next_state)
            else:
                if row['used'] >= 7 or not row['pending_level']:
                    raise ValueError('No claimable Flask gauge reward')
                template, quantity = settings()['bonuses'][row['pending_level']]
                rewards = {template: quantity}
                row.update(used=row['used']+1, gauge=0, pending_level=0)
            from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
            for template, quantity in sorted(rewards.items()):
                grant_items(db, [dict(template=template, metadata=VERIFIED_TEMPLATES[template],
                                      group=TEMPLATE_BAG_GROUPS[template], quantity=quantity)], owner)
            save(db, owner, row)
            after = load_items(db, owner)
            positions = _positions(items, after)
            right = {(i['group'], i['slot']): i for i in after}
            wire = acknowledgement(kind, ed=ed, state=projected(row, next_state), rewards=rewards,
                                   changes=[(p, right.get(p)) for p in positions], xp=xp)
            from els_server.storage.inventory_actions import _commit
            _commit(db, operation, digest, owner, kind, positions, items, after)
            events = [Event(0x201, kind=0x708 if kind == 0x707 else 0x9af, payload=wire)]
            if leveled:
                events.append(Event(0x201, kind=0x4c4, payload=level_update(owner, next_state, {})))
            events.append(Event(0x201, kind=0x9b0, payload=notification(projected(row, next_state))))
            events = _prepare(events, authorize, prepare)
            # Recheck the same authoritative character and lifecycle before commit.
            actor(db, owner, account_id)
            _authorize(authorize)
            db.commit()
            return dict(replayed=False, events=events, xp=xp, rewards=rewards,
                        quote=quote, state=asdict(next_state), ledger=row)
        except BaseException:
            db.rollback()
            raise


def observe(path, owner, account_id, *, now=None, authorize=None):
    """Read-only cold/periodic projection; no schema initialization or timer."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=10)) as db:
        db.execute('BEGIN')
        _authorize(authorize)
        _, state = actor(db, owner, account_id)
        row = ledger(db, owner, state, int(time.time()) if now is None else now)
        payload = notification(projected(row, state))
        _authorize(authorize)
        db.rollback()
        return payload
