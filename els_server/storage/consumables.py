"""Owned stack consumption and cooldown commit together; effects emit once."""
from contextlib import closing
import hashlib,math,sqlite3,time
from els_server.storage.character_schema import character_uid
from els_server.storage.quick_slots import _load
from els_server.storage.inventory_state import load_items
from els_server.domain.quick_bindings import item_binding
from els_server.domain.consumables import require_usable,recovery_cooldown_seconds
from els_server.protocol.consumable_messages import request,acknowledgement,effect


def use(path,uid,payload,operation_id,*,now=None,automatic_use=False):
    uid=character_uid(uid)
    slot=request(payload,automatic=automatic_use)
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=160:raise ValueError('Consumable operation identity')
    now=time.time() if now is None else now
    if not isinstance(now,(int,float)) or not math.isfinite(now) or now<0:raise ValueError('Consumable clock')
    digest=hashlib.sha256(str(uid).encode()+b':'+bytes([automatic_use])+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        character=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()
        if character is None:raise ValueError('Unknown consumable owner')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='consumable_uses'").fetchone():
            old=db.execute('SELECT request_hash FROM consumable_uses WHERE operation_id=?',(operation_id,)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Conflicting consumable retry')
                # Clear a pending wait without reapplying healing, an obsolete
                # inventory decrement or a fresh cooldown. Login restores counts.
                return [acknowledgement(automatic=automatic_use,slot=slot)]
        if automatic_use:
            from els_server.storage.pet_support import automatic
            state=automatic(db,uid)
            active=db.execute('SELECT pet FROM companion_active WHERE owner=?',(uid,)).fetchone() if db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_active'").fetchone() else None
            if not state['automatic'] or not active or not active[0] or (state['upgrade'] and not state['enabled']):raise ValueError('Active pet and automatic entitlement required')
            binding=state['hp_binding' if slot==0 else 'mp_binding']
            interval=state['hp_seconds' if slot==0 else 'mp_seconds'] if state['upgrade'] else 0
            db.execute('CREATE TABLE IF NOT EXISTS pet_auto_cooldowns (owner INTEGER NOT NULL,slot INTEGER NOT NULL,ready_at REAL NOT NULL,PRIMARY KEY(owner,slot))')
            last=db.execute('SELECT ready_at FROM pet_auto_cooldowns WHERE owner=? AND slot=?',(uid,slot)).fetchone()
            if last and now<last[0]:raise ValueError('Pet automatic timer has not elapsed')
        else:binding=_load(db,uid)[slot]
        if not binding:raise ValueError('Empty shortcut')
        from els_server.domain.item_expiration import expired
        matches=[i for i in load_items(db,uid) if i['group']==6 and item_binding(i['template'])==binding and not expired(i,now=int(now))]
        if not matches:raise ValueError('No owned consumable')
        # Multiple equivalent templates require the native selection priority.
        if len({i['template'] for i in matches})!=1:raise ValueError('Ambiguous consumable template')
        item=min(matches,key=lambda i:i['slot']);meta=require_usable(item['template'],character[0])
        db.execute('CREATE TABLE IF NOT EXISTS consumable_cooldowns (owner INTEGER NOT NULL REFERENCES characters(uid), cooldown_group INTEGER NOT NULL, ready_at REAL NOT NULL, PRIMARY KEY(owner,cooldown_group))')
        prior=db.execute('SELECT ready_at FROM consumable_cooldowns WHERE owner=? AND cooldown_group=?',(uid,meta['cooldown_group'])).fetchone()
        if prior and now<prior[0]:raise ValueError('Consumable is cooling down')
        remaining=dict(item,count=item['count']-1) if item['count']>1 else None
        answer=[acknowledgement(remaining,(item['group'],item['slot']),item['template'],automatic=automatic_use,slot=slot),effect(uid,item['template'])]
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item['uid'],uid))
        else:
            from els_server.storage.item_expiration import forget
            forget(db,item['uid'])
            db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item['uid'],uid))
        from els_server.storage.pet_support import active_effects
        reduction=max(0,min(.9,active_effects(db,uid).get('m_fReduceRecoveryItemCooltime',0)))
        db.execute('INSERT INTO consumable_cooldowns VALUES (?,?,?) ON CONFLICT(owner,cooldown_group) DO UPDATE SET ready_at=excluded.ready_at',(uid,meta['cooldown_group'],now+recovery_cooldown_seconds(meta['cooldown_seconds'],reduction)))
        if automatic_use:db.execute('INSERT INTO pet_auto_cooldowns VALUES (?,?,?) ON CONFLICT(owner,slot) DO UPDATE SET ready_at=excluded.ready_at',(uid,slot,now+interval))
        db.execute('CREATE TABLE IF NOT EXISTS consumable_uses (operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, owner INTEGER NOT NULL, item_uid INTEGER NOT NULL, template INTEGER NOT NULL, used_at REAL NOT NULL)')
        db.execute('INSERT INTO consumable_uses VALUES (?,?,?,?,?,?)',(operation_id,digest,uid,item['uid'],item['template'],now))
        return answer
