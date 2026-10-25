"""Optional explicit native seal state attached to owned inventory instances."""
def validate(sealed,used):
    if type(sealed) is not bool or type(used) is not int or not 0<=used<=(155 if sealed else 99):raise ValueError('Seal byte range')

def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS item_seals (item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,sealed INTEGER NOT NULL CHECK(sealed IN(0,1)),used INTEGER NOT NULL CHECK(used>=0 AND used<=155))')

def attach(db,items,owner):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='item_seals' AND type='table'").fetchone():return
    by_uid={i['uid']:i for i in items}
    for uid,sealed,used in db.execute('SELECT s.item_uid,s.sealed,s.used FROM item_seals s JOIN inventory_items i ON i.uid=s.item_uid WHERE i.owner=?',(owner,)):
        if uid in by_uid:
            if sealed not in (0,1):raise ValueError('Corrupt seal flag')
            validate(bool(sealed),used);by_uid[uid].update(sealed=bool(sealed),seal_used=used)

def assign(db,owner,uid,sealed,used):
    if not db.in_transaction:raise ValueError('Seal assignment requires transaction')
    from els_server.domain.cartridge_registration_rules import require_unbound
    require_unbound(db,uid)
    validate(sealed,used)
    if db.execute('SELECT 1 FROM inventory_items WHERE uid=? AND owner=?',(uid,owner)).fetchone() is None:raise ValueError('Seal owner mismatch')
    ensure(db);db.execute('INSERT INTO item_seals VALUES(?,?,?) ON CONFLICT(item_uid) DO UPDATE SET sealed=excluded.sealed,used=excluded.used',(uid,int(sealed),used))


def _target(item,*,sealing):
    from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
    from els_server.domain.normal_equipment import definitions
    from els_server.domain.ordinary_accessories import definitions as accessory_definitions
    from els_server.domain.artifact_progression import slots as artifact_slots
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    from els_server.game_data import client_data
    if (item is None or item['count'] != 1 or
            not (item['group'] == 1 and (item['template'] in definitions() or artifact_slots(item['template'])) or
                 item['group'] == 2 and item['template'] in accessory_definitions() or
                 item['group'] in (7, 27) and item['template'] in FASHION_EQUIP_SLOTS)):
        raise ValueError('Seal operation requires owned bag equipment')
    require_current(item)
    require_unlocked(item)
    if sealing and item.get('wardrobe_hanger',False):
        raise ValueError('Wardrobe hanger cannot be resealed')
    if item.get('identified') is False:
        raise ValueError('Unidentified seal target')
    raw = client_data().item(item['template'])['record']
    if not raw[4] & 2 or (raw[8] >> 3) & 31 not in (1, 2, 3):
        raise ValueError('Unsupported seal target definition')
    return raw


def change_seal(path, owner, payload, operation, *, sealing):
    """270/272 on one owned UID, with inventory-action receipts and rollback."""
    import sqlite3
    from contextlib import closing
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    from els_server.protocol.inventory_management_messages import seal_request, unseal_request, seal_ack
    from els_server.storage.inventory_actions import _identity, _previous, _commit
    from els_server.storage.inventory_state import load_items
    if type(sealing) is not bool:
        raise ValueError('Seal operation direction')
    target_uid, stamp_uid = seal_request(payload) if sealing else (unseal_request(payload), None)
    kind = 0x270 if sealing else 0x272
    owner, digest = _identity(owner, kind, payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        old = _previous(db, operation, digest)
        before = load_items(db, owner)
        if old is not None:
            # Retain current replacement occupants in historical slots and
            # refresh the original target/stamp UIDs at their present slots.
            # Replays never reapply the old seal state or consume a stamp.
            from els_server.storage.equipment_receipt_state import current_changes
            return seal_ack(current_changes(db, operation, owner, kind, old, before))
        by_uid = {i['uid']: i for i in before}
        target = by_uid.get(target_uid)
        raw = _target(target,sealing=sealing)
        from els_server.domain.cartridge_registration_rules import require_unbound
        require_unbound(db,target_uid)
        sealed, used = target.get('sealed', False), target.get('seal_used', 0)
        validate(sealed, used)
        positions = [(target['group'], target['slot'])]
        if sealing:
            maximum = raw[0xd7]
            # Original2247FA2 admits FF as a special case; its counter policy
            # is not established. Leave that branch closed without clamping.
            if sealed or not 1 <= maximum <= 99 or used >= maximum or 'expires_at' in target:
                raise ValueError('Target already sealed, exhausted, timed or special')
            # Original22481D3..22481FC: durable weapon/armour must be fully
            # repaired before sealing. Missing historical durability is zero.
            if ((raw[8] >> 3) & 31 in (1, 2) and
                    int.from_bytes(raw[4:8], 'little') & 0xf000000 == 0x1000000 and
                    target.get('durability', 0) != int.from_bytes(raw[0xc8:0xca], 'little', signed=True)):
                raise ValueError('Seal target requires full native durability')
            stamp = by_uid.get(stamp_uid)
            from els_server.domain.item_sealing_rules import accepts
            if (stamp is None or stamp['group'] != 4 or
                    not accepts(stamp['template'], raw) or
                    stamp.get('sealed', False) or stamp.get('seal_used', 0)):
                raise ValueError('Missing or incompatible original stamp')
            require_current(stamp)
            require_unlocked(stamp)
            positions.append((stamp['group'], stamp['slot']))
            # One ordinary stamp buys one seal. Resealing consumes one use;
            # removing it never restores uses. No ED is charged by this UI.
            assign(db, owner, target_uid, True, used + 1)
            if stamp['count'] > 1:
                db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?', (stamp_uid, owner))
            else:
                from els_server.storage.item_expiration import forget as forget_expiration
                from els_server.storage.item_locks import forget as forget_lock
                forget_expiration(db, stamp_uid)
                forget_lock(db, stamp_uid)
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_seals'").fetchone():
                    db.execute('DELETE FROM item_seals WHERE item_uid=?', (stamp_uid,))
                db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?', (stamp_uid, owner))
        else:
            # Used>=100 cannot be encoded as an unsealed item by the native
            # decimal-byte representation. Preserve it and reject, never wrap.
            if not sealed or used > 99:
                raise ValueError('Target unsealed or unsupported seal history')
            assign(db, owner, target_uid, False, used)
        current = load_items(db, owner)
        by_position = {(i['group'], i['slot']): i for i in current}
        answer = seal_ack([(p, by_position.get(p)) for p in positions])
        _commit(db, operation, digest, owner, kind, positions, before, current)
        return answer
