"""Owned stack consumption and cooldown commit together; effects emit once."""
from contextlib import closing
import hashlib,math,sqlite3,time
from els_server.storage.character_schema import character_uid
from els_server.storage.quick_slots import _load
from els_server.storage.inventory_state import load_quick_items
from els_server.domain.quick_bindings import item_binding
from els_server.domain.consumables import (AUTOMATIC_STAGE_VARIANTS, CURRENT_MANUAL,
    ConsumableCoolingDown, recovery_cooldown_seconds, require_usable)
from els_server.protocol.consumable_messages import request,acknowledgement,effect
from els_server.protocol.protocol_codec import encode_event
from els_server.domain.consumable_extensions import quick_templates,quick_bindings,infinite
from els_server.domain.item_expiration import expired
from els_server.domain.item_locks import locked


# Original binding representatives for the groups with mixed template keys.
AUTOMATIC_COOLDOWN_KEYS = {412: (710000, 15), 415: (710021, 19)}


def automatic_item(item, now):
    return item['group']==6 and not item.get('sealed') and not expired(item,now=now) and not locked(item,now=now)


def use(path,uid,payload,operation_id,*,now=None,automatic_use=False,allow_apples=False,account_id=None,mount_only=False,authorize=None,after_manual_use=None):
    uid=character_uid(uid)
    slot=request(payload,automatic=automatic_use)
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=160:raise ValueError('Consumable operation identity')
    digest=hashlib.sha256(str(uid).encode()+b':'+bytes([automatic_use])+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        if authorize is not None:authorize(db)
        # Expiration is authoritative after any wait for the real writer lock.
        now=time.time() if now is None else now
        if not isinstance(now,(int,float)) or not math.isfinite(now) or now<0:raise ValueError('Consumable clock')
        character=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()
        if character is None:raise ValueError('Unknown consumable owner')
        if account_id is not None:
            from els_server.storage.profession_state import require_owner
            require_owner(db,uid,account_id)
        from els_server.storage.character_lifecycle import exists as lifecycle_exists
        if lifecycle_exists(db):
            lifecycle=db.execute('SELECT requested_at,finalized_at FROM character_lifecycle WHERE uid=?',(uid,)).fetchone()
            if lifecycle and any(lifecycle):raise ValueError('Unavailable consumable character')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='consumable_uses'").fetchone():
            old=db.execute('SELECT request_hash FROM consumable_uses WHERE operation_id=?',(operation_id,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Conflicting consumable retry')
                # Clear a pending wait without reapplying healing, an obsolete
                # inventory decrement or a fresh cooldown. Login restores counts.
                return [acknowledgement(automatic=automatic_use,slot=slot)]
        if automatic_use:
            from els_server.storage.pet_support import automatic
            state=automatic(db,uid,now=int(now))
            active=db.execute('SELECT pet FROM companion_active WHERE owner=?',(uid,)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_active'").fetchone() else None
            if not state['automatic'] or not active or not active[0] or (state['upgrade'] and not state['enabled']):raise ValueError('Active pet and automatic entitlement required')
            from els_server.storage.pet_support import owned_pet
            owned_pet(db,uid,active[0])
            binding=state['hp_binding' if slot==0 else 'mp_binding']
            interval=state['hp_seconds' if slot==0 else 'mp_seconds'] if state['upgrade'] else 0
            db.execute('CREATE TABLE IF NOT EXISTS pet_auto_cooldowns (owner INTEGER NOT NULL,slot INTEGER NOT NULL,ready_at REAL NOT NULL,PRIMARY KEY(owner,slot))')
            last=db.execute('SELECT ready_at FROM pet_auto_cooldowns WHERE owner=? AND slot=?',(uid,slot)).fetchone()
            if last and now<last[0]:raise ConsumableCoolingDown('Pet automatic timer has not elapsed',slot=slot)
        else:binding=_load(db,uid)[slot]
        if not binding:raise ValueError('Empty shortcut')
        items=load_quick_items(db,uid,binding)
        stamp=int(now)
        if automatic_use:
            matches=[i for i in items if automatic_item(i,stamp)]
        else:
            matches=[i for i in items
                     if not expired(i,now=stamp) and not locked(i,now=stamp)]
        if not matches:raise ValueError('No owned consumable')
        stage_templates={710313,710314,710315,77110,130467,710193,723674,190624,710010}|quick_templates()|CURRENT_MANUAL
        if automatic_use:
            stage_templates |= AUTOMATIC_STAGE_VARIANTS
        if binding in ({399,775}|quick_bindings()|{item_binding(t)for t in CURRENT_MANUAL}):
            # Approved local policy: only currently usable owned instances;
            # earliest finite expiry, permanent last, then bag slot and UID.
            eligible=[]
            for candidate in matches:
                try:
                    metadata=require_usable(candidate['template'],character[0],automatic=automatic_use)
                except ValueError:continue
                if candidate['template'] in stage_templates and allow_apples is not True:continue
                eligible.append((candidate,metadata))
            if not eligible:raise ValueError('No eligible owned consumable')
            item,meta=min(eligible,key=lambda entry:('expires_at' not in entry[0],
                entry[0].get('expires_at',0),entry[0]['slot'],entry[0]['uid']))
        else:
            # Other binding groups retain their existing source boundary.
            if len({i['template'] for i in matches})!=1:raise ValueError('Ambiguous consumable template')
            item=min(matches,key=lambda i:i['slot'])
            meta=require_usable(item['template'],character[0],automatic=automatic_use)
            if item['template'] in stage_templates and allow_apples is not True:
                raise ValueError('Apple native actor stage is not ready')
        if mount_only and(automatic_use or item['template']!=185080):raise ValueError('Only native mount fuel may use this town route')
        cooldown_template = item['template']
        cooldown_group = meta['cooldown_group']
        if automatic_use and binding in AUTOMATIC_COOLDOWN_KEYS:
            # The native pet request checks the representative of the binding.
            # Keep the inventory record and effect tied to the consumed instance.
            representative, native_group = AUTOMATIC_COOLDOWN_KEYS[binding]
            if cooldown_group != native_group:
                cooldown_template, cooldown_group = representative, native_group
        # Native 3055590 keeps automatic recovery groups at +140 and manual
        # recovery groups at +130; the pet's configured slot timers are separate.
        if automatic_use:
            db.execute('CREATE TABLE IF NOT EXISTS pet_consumable_cooldowns (owner INTEGER NOT NULL REFERENCES characters(uid), cooldown_group INTEGER NOT NULL, ready_at REAL NOT NULL, PRIMARY KEY(owner,cooldown_group))')
            prior=db.execute('SELECT ready_at FROM pet_consumable_cooldowns WHERE owner=? AND cooldown_group=?',(uid,cooldown_group)).fetchone()
        else:
            db.execute('CREATE TABLE IF NOT EXISTS consumable_cooldowns (owner INTEGER NOT NULL REFERENCES characters(uid), cooldown_group INTEGER NOT NULL, ready_at REAL NOT NULL, PRIMARY KEY(owner,cooldown_group))')
            prior=db.execute('SELECT ready_at FROM consumable_cooldowns WHERE owner=? AND cooldown_group=?',(uid,cooldown_group)).fetchone()
        if prior and now<prior[0]:raise ConsumableCoolingDown('Consumable is cooling down',slot=slot)
        unlimited=infinite(item['template'])
        if unlimited and(item['metadata']!=0 or item['count']!=1):raise ValueError('Native infinite item instance')
        if item['template']==185080:
            from els_server.domain.guild_mount_fuel import apply
            apply(db,uid,int(now))
        from els_server.storage.pet_support import active_effects
        from els_server.domain.recovery_item_cooldown import FIELD, LIMIT, worn_reduction
        reduction=active_effects(db,uid).get(FIELD,0)
        if not mount_only and meta['cooldown_seconds']:
            reduction=min(LIMIT,reduction+worn_reduction(db,uid,items,int(now)))
        reduction=max(0,min(.9,reduction))
        duration=recovery_cooldown_seconds(meta['cooldown_seconds'],reduction)
        remaining=dict(item)if unlimited else dict(item,count=item['count']-1)if item['count']>1 else None
        # Native 3055590 uses this override for the pet's +140 cooldown map.
        # Its local actor modifiers need not equal the server's admitted inputs.
        answer=[acknowledgement(remaining,(item['group'],item['slot']),cooldown_template,cooldown=duration if automatic_use else -1.0,automatic=automatic_use,slot=slot),effect(uid,item['template'])]
        # Validate complete native envelopes before any debit or cooldown write.
        for event in answer:encode_event(event)
        if unlimited:pass  # Native SAT_INFINITE_QUANTITY_ITEM65: keep exact instance.
        elif remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],uid))
        else:
            from els_server.storage.item_instances import remove
            remove(db,uid,item)
        if automatic_use:
            db.execute('INSERT INTO pet_auto_cooldowns VALUES (?,?,?) ON CONFLICT(owner,slot) DO UPDATE SET ready_at=excluded.ready_at',(uid,slot,now+interval))
            db.execute('INSERT INTO pet_consumable_cooldowns VALUES (?,?,?) ON CONFLICT(owner,cooldown_group) DO UPDATE SET ready_at=excluded.ready_at',(uid,cooldown_group,now+duration))
        else:
            db.execute('INSERT INTO consumable_cooldowns VALUES (?,?,?) ON CONFLICT(owner,cooldown_group) DO UPDATE SET ready_at=excluded.ready_at',(uid,cooldown_group,now+duration))
        db.execute('CREATE TABLE IF NOT EXISTS consumable_uses (operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, owner INTEGER NOT NULL, item_uid INTEGER NOT NULL, template INTEGER NOT NULL, used_at REAL NOT NULL)')
        db.execute('INSERT INTO consumable_uses VALUES (?,?,?,?,?,?)',(operation_id,digest,uid,item['uid'],item['template'],now))
        if after_manual_use is not None and not automatic_use:
            mission=after_manual_use(db,operation_id,int(now))
            for event in mission:encode_event(event)
            answer.extend(mission)
        if authorize is not None:authorize(db)
        return answer
