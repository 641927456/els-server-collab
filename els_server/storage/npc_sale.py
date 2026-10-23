"""Atomic NPC sales; request retries return current slots and current money."""
from els_server.storage.item_actor import require_active_character
import sqlite3
import struct
from contextlib import closing
from els_server.domain.npc_sale import unit_price
from els_server.domain.inventory_items import validate_item
from els_server.protocol.npc_sale_messages import request, acknowledgement
from els_server.protocol.protocol_codec import Event
from els_server.storage.inventory_state import load_items
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_management import _updates
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.reward_state import validate_balances
from els_server.storage.item_expiration import forget as forget_expiration
from els_server.storage.item_locks import forget as forget_lock


def sell(path, owner, payload, operation, session='local'):
    entries, merchant = request(payload)
    # The native random padding is not transaction identity. A retransmission
    # that regenerated padding still refers to the same UID/count/merchant.
    canonical = (struct.pack('>I', len(entries)) + b''.join(struct.pack('>Qi', *e) for e in entries)
                 + struct.pack('>i', merchant))
    owner, digest = _identity(owner, 0xec, canonical, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE');require_active_character(db,owner)
        old = _previous(db, operation, digest)
        before = load_items(db, owner)
        balance = validate_balances(db.execute(
            'SELECT ed,experience,revision FROM reward_balances WHERE uid=?', (owner,)).fetchone())
        if old is not None:
            # Sending sold rows again would duplicate native repurchase entries.
            return [Event(0x201, kind=0xed, payload=acknowledgement(balance['ed']))] + _updates(
                current_changes(db,operation,owner,0xec,old,before))
        by_uid = {i['uid']: i for i in before}
        selected, changes, sold = [], [], []
        income = 0
        for uid, quantity in entries:
            item = by_uid.get(uid)
            if item is None or quantity > item['count']:
                raise ValueError('Sale exceeds owned item count')
            from els_server.domain.cartridge_registration_rules import require_unbound
            require_unbound(db,uid)
            price = unit_price(item)
            # Native 2C5C600 multiplies signed int unit price and count.
            if price*quantity >= 2**31:
                raise ValueError('Sale line exceeds native signed amount')
            income += price*quantity
            selected.append(item)
            remaining = validate_item(dict(item, count=item['count']-quantity)) if quantity < item['count'] else None
            changes.append(((item['group'], item['slot']), remaining))
            sold.append(validate_item(dict(item, count=quantity)))
        total = balance['ed'] + income
        if total >= 2**63 or balance['revision'] >= 2**63-1:
            raise ValueError('Sale balance overflow')
        # 2C5C6D5..2C5C7DA uses service+480's level ED limit before
        # native sale submission. Keep the same authority for forged requests;
        # committed retries above returned before this new-operation check.
        from els_server.domain.bank_rules import player_ed_limit
        row=(db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()
             if db.execute("SELECT 1 FROM sqlite_master WHERE name='characters'").fetchone() else (1,))
        if row is None or total>player_ed_limit(row[0]):
            raise ValueError('Sale exceeds character ED carrying limit')
        # Encode before changing persistent state; all failures roll back.
        wire = acknowledgement(total, changes, sold)
        for item, (_, remaining) in zip(selected, changes):
            if remaining is not None:
                db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?',
                           (remaining['count'], item['uid'], owner))
            else:
                for table in ('equipment_attributes', 'equipment_durability', 'equipment_enhancement', 'equipment_options', 'equipment_identification', 'equipment_enhancement_progress', 'item_seals'):
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                        db.execute(f'DELETE FROM {table} WHERE item_uid=?', (item['uid'],))
                forget_expiration(db, item['uid'])
                forget_lock(db, item['uid'])
                db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?', (item['uid'], owner))
        db.execute('UPDATE reward_balances SET ed=?,revision=revision+1 WHERE uid=?', (total, owner))
        from els_server.storage.npc_trade import remember
        remember(db, owner, session, sold)
        after = load_items(db, owner)
        _commit(db, operation, digest, owner, 0xec, [p for p, item in changes], before, after)
        return [Event(0x201, kind=0xed, payload=wire)]
