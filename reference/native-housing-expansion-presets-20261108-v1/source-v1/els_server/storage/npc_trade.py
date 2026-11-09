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
from els_server.storage.item_instances import next_uid, insert, uid_reserved, read_stored, bag_group, reduce_count


def ensure_history(db):
    db.execute('''CREATE TABLE IF NOT EXISTS npc_sale_history (
        id INTEGER PRIMARY KEY, session TEXT NOT NULL, owner INTEGER NOT NULL,
        item_json TEXT NOT NULL)''')


def history(db, owner, session):
    if not isinstance(session, str) or not 1 <= len(session) <= 160:
        raise ValueError('Merchant history session identity')
    ensure_history(db)
    return [(key, validate_item(read_stored(json.loads(item)))) for key, item in db.execute(
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


class InsufficientED(ValueError):
    pass


def charge(db, owner, balance, amount):
    if not 0 <= amount or balance['revision'] >= 2**63-1:
        raise ValueError('Merchant money or revision bound')
    if amount > balance['ed']:
        raise InsufficientED('Merchant ED insufficient')
    db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=?', (amount, owner))
    return balance['ed']-amount


def purchase(path, owner, town, payload, operation, *, guild_account_id=None, guild_guard=None):
    entries, merchant = purchase_request(payload)
    owner, digest = _identity(owner, 0xea, struct.pack('>i', town)+payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON'); db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        from els_server.storage import guild_license_purchase as guild_license
        guild_bound = guild_license.context(db,owner,guild_account_id,town,merchant,entries,guild_guard)
        old = _previous(db, operation, digest)
        before = load_items(db, owner); balance = balances(db, owner)
        if old is not None:
            events = [Event(0x201, kind=0xeb, payload=purchase_ack(balance['ed']))]+_updates(current_changes(db,operation,owner,0xea,old,before))
            return guild_license.precommit(events,guild_guard) if guild_bound else events
        from els_server.domain import spa_market
        spa_cycle=spa_market.new_purchase(db,owner,town,entries,merchant)
        if guild_bound:guild_license.new_purchase(db,owner,guild_account_id,before)
        from els_server.domain.furniture_rules import BOX_TEMPLATES,NPC_POLICY
        furniture = [dict(template=t,metadata=VERIFIED_TEMPLATES[t],quantity=q,
                          group=TEMPLATE_BAG_GROUPS[t]) for t,q in entries if t in BOX_TEMPLATES]
        source = None
        if furniture:
            from els_server.domain.raid_reward_items import _issue_source
            def current_merchant(db):
                require_active_character(db,owner)
                return db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()==(town,)
            source = _issue_source(db,owner,operation,'npc_trade',
                dict(policy=NPC_POLICY,owner=owner,operation=operation,town=town,merchant=merchant),
                furniture,current_merchant)
        amount = sum(offer(town,merchant,t,raid_reward_source=source if t in BOX_TEMPLATES else None)*q for t,q in entries)
        if amount >= 2**31:
            raise ValueError('Merchant native signed price overflow')
        ed = charge(db, owner, balance, amount)
        ordinary = [dict(template=t,metadata=VERIFIED_TEMPLATES[t],quantity=q,
                         group=TEMPLATE_BAG_GROUPS[t]) for t,q in entries if t not in BOX_TEMPLATES]
        changes = grant_items(db,ordinary,owner) if ordinary else []
        if furniture:changes += grant_items(db,furniture,owner,raid_reward_source=source)
        wire = purchase_ack(ed, changes)
        after = load_items(db, owner)
        _commit(db, operation, digest, owner, 0xea, [(i['group'], i['slot']) for i in changes], before, after)
        events = [Event(0x201, kind=0xeb, payload=wire)]
        if spa_cycle is not None:spa_market.require_open(spa_cycle)
        return guild_license.precommit(events,guild_guard) if guild_bound else events


def _signature(item):
    return {k:v for k,v in item.items() if k not in ('uid','group','slot','count')}


def _return_sold(item, quantity, uid, slot, current=None):
    """Return a bounded historical source, consumed in this same transaction."""
    validate_item(item)
    if type(quantity)is not int or not 0<quantity<=item['count']:
        raise ValueError('Buyback return exceeds historical source')
    returned=dict(item,uid=uid,count=quantity,group=bag_group(item),slot=slot)
    if current is not None:
        validate_item(current)
        if (current['uid']!=uid or current['slot']!=slot or current['group']!=returned['group']
            or _signature(current)!=_signature(item)):
            raise ValueError('Buyback destination differs from historical source')
        returned['count']+=current['count']
    # Only the owned history above supplies this transfer; no acquisition
    # registry or ordinary retained-item producer is opened by the adapter.
    return validate_item(read_stored(returned))


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
        if quantity > item['count'] or supplied != record(reduce_count(item,quantity) if quantity < item['count'] else item):
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
        group = bag_group(item)
        remaining=quantity;changes=[]
        maximum=TEMPLATE_MAX_STACKS.get(item['template'],1)
        if maximum>1:
            for current in before:
                if current['group']!=group or _signature(current)!=_signature(item):continue
                delta=min(remaining,maximum-current['count'])
                if delta<=0:continue
                current=_return_sold(item,delta,current['uid'],current['slot'],current);remaining-=delta
                db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?',(current['count'],current['uid'],owner))
                changes.append(current)
                if not remaining:break
        if remaining:
            slot = next((n for n in range(allowances(db, owner)[group]) if (group, n) not in occupied), None)
            if slot is None:raise InventoryFull('Repurchase needs a free bag slot')
            # Preserve a complete sold instance's UID unless another container
            # still owns it; a partial stack then receives a fresh UID.
            uid = next_uid(db) if uid_reserved(db,item['uid']) else item['uid']
            changes.append(insert(db, owner, _return_sold(item,remaining,uid,slot)))
        if quantity == item['count']:
            db.execute('DELETE FROM npc_sale_history WHERE id=?', (key,))
        else:
            db.execute('UPDATE npc_sale_history SET item_json=? WHERE id=?', (json.dumps(reduce_count(item,item['count']-quantity), sort_keys=True), key))
        wire = repurchase_ack(ed, index, quantity, changes)
        after = load_items(db, owner)
        _commit(db, operation, digest, owner, 0x567, [(i['group'], i['slot']) for i in changes], before, after)
        return [Event(0x201, kind=0x568, payload=wire)]
