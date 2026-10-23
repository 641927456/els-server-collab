"""Atomic stock purchases and session-scoped, eight-entry native buyback."""
from els_server.storage.item_actor import require_active_character
import json
import sqlite3
import struct
from contextlib import closing
from els_server.domain.npc_trade import offer, price, stock
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS, TEMPLATE_MAX_STACKS, validate_item
from els_server.domain.item_expiration import require_current
from els_server.domain.fashion_state import record
from els_server.protocol.npc_trade_messages import purchase_request, purchase_ack, repurchase_request, repurchase_ack
from els_server.protocol.protocol_codec import Event
from els_server.protocol.npc_sale_messages import acknowledgement as sale_ack
from els_server.storage.inventory_state import load_items, grant_items, InventoryFull
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_management import _updates
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.reward_state import validate_balances
from els_server.storage.bag_capacity import allowances
from els_server.storage.item_instances import next_uid, insert, uid_in_use


def ensure_history(db):
    db.execute('''CREATE TABLE IF NOT EXISTS npc_sale_history (
        id INTEGER PRIMARY KEY, session TEXT NOT NULL, owner INTEGER NOT NULL,
        item_json TEXT NOT NULL)''')


def history(db, owner, session):
    if not isinstance(session, str) or not 1 <= len(session) <= 160:
        raise ValueError('Merchant history session identity')
    ensure_history(db)
    return [(key, validate_item(json.loads(item))) for key, item in db.execute(
        'SELECT id,item_json FROM npc_sale_history WHERE session=? AND owner=? ORDER BY id', (session, owner))]


def remember(db, owner, session, items):
    history(db, owner, session)
    for item in items:
        db.execute('INSERT INTO npc_sale_history(session,owner,item_json) VALUES (?,?,?)',
            (session, owner, json.dumps(validate_item(item), sort_keys=True)))
    db.execute('''DELETE FROM npc_sale_history WHERE session=? AND owner=? AND id NOT IN
        (SELECT id FROM npc_sale_history WHERE session=? AND owner=? ORDER BY id DESC LIMIT 8)''',
        (session, owner, session, owner))


def balances(db, owner):
    return validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?', (owner,)).fetchone())


def charge(db, owner, balance, amount):
    if not 0 <= amount <= balance['ed'] or balance['revision'] >= 2**63-1:
        raise ValueError('Merchant money or revision bound')
    db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=?', (amount, owner))
    return balance['ed']-amount


def purchase(path, owner, town, payload, operation):
    entries, merchant = purchase_request(payload)
    owner, digest = _identity(owner, 0xea, struct.pack('>i', town)+payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON'); db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        old = _previous(db, operation, digest)
        before = load_items(db, owner); balance = balances(db, owner)
        if old is not None:
            return [Event(0x201, kind=0xeb, payload=purchase_ack(balance['ed']))]+_updates(current_changes(db,operation,owner,0xea,old,before))
        amount = sum(offer(town, merchant, t)*q for t, q in entries)
        if amount >= 2**31:
            raise ValueError('Merchant native signed price overflow')
        ed = charge(db, owner, balance, amount)
        changes = grant_items(db, [dict(template=t, metadata=VERIFIED_TEMPLATES[t],
            quantity=q, group=TEMPLATE_BAG_GROUPS[t]) for t, q in entries], owner)
        wire = purchase_ack(ed, changes)
        after = load_items(db, owner)
        _commit(db, operation, digest, owner, 0xea, [(i['group'], i['slot']) for i in changes], before, after)
        return [Event(0x201, kind=0xeb, payload=wire)]


def repurchase(path, owner, payload, operation, session='local', town=None):
    index, quantity, merchant, supplied = repurchase_request(payload)
    owner, digest = _identity(owner, 0x567, session.encode()+b'\0'+payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON'); db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        old = _previous(db, operation, digest)
        before = load_items(db, owner); balance = balances(db, owner)
        if old is not None:
            # A success 568 would remove history a second time. A non-success
            # response clears its native wait without indexing history again.
            return [Event(0x201, kind=0x568, payload=repurchase_ack(balance['ed'], result=-1)),
                Event(0x201, kind=0xed, payload=sale_ack(balance['ed']))]+_updates(current_changes(db,operation,owner,0x567,old,before))
        if town is not None and (town,merchant) not in stock():
            raise ValueError('Repurchase merchant is not in the current town')
        sold = history(db, owner, session)
        if index >= len(sold):
            raise ValueError('Repurchase history no longer contains index')
        key, item = sold[index]
        if quantity > item['count'] or supplied != record(dict(item, count=quantity)):
            raise ValueError('Repurchase instance/count differs from server history')
        if not any(npc == merchant for town, npc in stock()):
            raise ValueError('Repurchase merchant identity')
        require_current(item)
        # Retail's buyback preflight uses template+1C, not the 20% sale value.
        amount = price(item['template'], repurchase=True)*quantity
        if amount >= 2**31:
            raise ValueError('Repurchase native signed price overflow')
        ed = charge(db, owner, balance, amount)
        occupied = {(i['group'], i['slot']) for i in before}
        group = TEMPLATE_BAG_GROUPS[item['template']]
        remaining=quantity;changes=[]
        signature=lambda i:{k:v for k,v in i.items() if k not in ('uid','group','slot','count')}
        maximum=TEMPLATE_MAX_STACKS[item['template']]
        if maximum>1:
            for current in before:
                if current['group']!=group or signature(current)!=signature(item):continue
                delta=min(remaining,maximum-current['count'])
                if delta<=0:continue
                current=validate_item(dict(current,count=current['count']+delta));remaining-=delta
                db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?',(current['count'],current['uid'],owner))
                changes.append(current)
                if not remaining:break
        if remaining:
            slot = next((n for n in range(allowances(db, owner)[group]) if (group, n) not in occupied), None)
            if slot is None:raise InventoryFull('Repurchase needs a free bag slot')
            # Preserve a complete sold instance's UID unless another container
            # still owns it; a partial stack then receives a fresh UID.
            uid = next_uid(db) if uid_in_use(db,item['uid']) else item['uid']
            changes.append(insert(db, owner, dict(item, uid=uid, count=remaining, group=group, slot=slot)))
        if quantity == item['count']:
            db.execute('DELETE FROM npc_sale_history WHERE id=?', (key,))
        else:
            db.execute('UPDATE npc_sale_history SET item_json=? WHERE id=?', (json.dumps(dict(item, count=item['count']-quantity), sort_keys=True), key))
        wire = repurchase_ack(ed, index, quantity, changes)
        after = load_items(db, owner)
        _commit(db, operation, digest, owner, 0x567, [(i['group'], i['slot']) for i in changes], before, after)
        return [Event(0x201, kind=0x568, payload=wire)]
