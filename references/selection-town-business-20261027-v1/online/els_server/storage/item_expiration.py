"""UID-owned deadlines; grants and removal share the existing inventory transaction."""
import json,sqlite3,time
from contextlib import closing
from els_server.domain.item_expiration import validate
from els_server.storage.character_schema import character_uid


def exists(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_expiration'").fetchone())


def attach(db,items,owner):
    if not exists(db):return items
    owned={i['uid']:i for i in items}
    for uid,deadline in db.execute('''SELECT e.item_uid,e.expires_at FROM item_expiration e
        JOIN inventory_items i ON i.uid=e.item_uid WHERE i.owner=?''',(owner,)):
        if uid in owned:owned[uid]['expires_at']=validate(deadline)
    return items


def assign(db,owner,item_uid,deadline):
    """Internal grant hook; never extends/replaces an existing deadline."""
    if not db.in_transaction:raise ValueError('Expiration requires explicit transaction')
    owner=character_uid(owner);deadline=validate(deadline)
    from els_server.domain.cartridge_registration_rules import require_unbound
    require_unbound(db,item_uid)
    if type(item_uid) is not int or not db.execute('SELECT 1 FROM inventory_items WHERE uid=? AND owner=?',(item_uid,owner)).fetchone():raise ValueError('Unknown owned timed item')
    db.execute('''CREATE TABLE IF NOT EXISTS item_expiration (
        item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,
        expires_at INTEGER NOT NULL)''')
    db.execute('INSERT INTO item_expiration VALUES (?,?)',(item_uid,deadline))


def forget(db,item_uid):
    if exists(db):db.execute('DELETE FROM item_expiration WHERE item_uid=?',(item_uid,))


def remove_due(path,owner,*,now=None,prepare_refresh=None,prepare_remaining_refresh=None):
    from els_server.storage.inventory_state import load_items
    from els_server.protocol.expiration_messages import notice
    owner=character_uid(owner);now=int(time.time()) if now is None else now
    if type(now) is not int or now<0:raise ValueError('Invalid expiration clock')
    with closing(sqlite3.connect(path,timeout=10)) as db:
        if not exists(db):return []
        # Idle maintenance is a read. Keep the owner-qualified probe in a
        # consistent snapshot, then release it before taking the writer lock.
        # The second query below is authoritative after any intervening write.
        db.execute('BEGIN')
        if not db.execute('''SELECT 1 FROM item_expiration e
            JOIN inventory_items i ON i.uid=e.item_uid
            WHERE i.owner=? AND e.expires_at<? LIMIT 1''',(owner,now)).fetchone():return []
        db.rollback()
        with write_transaction(db):
            due={r[0] for r in db.execute('''SELECT e.item_uid FROM item_expiration e
                JOIN inventory_items i ON i.uid=e.item_uid WHERE i.owner=? AND e.expires_at<?''',(owner,now))}
            if not due:return []
            owned=load_items(db,owner)
            items=[i for i in owned if i['uid'] in due]
            from els_server.domain.cartridge_registration_rules import require_unbound
            for item in items:require_unbound(db,item['uid'])
            answer=notice(items) # Validate/encode before any committed deletion.
            if prepare_refresh is not None and prepare_remaining_refresh is not None:raise ValueError('Ambiguous expiration refresh')
            prepared=(prepare_remaining_refresh(items,[i for i in owned if i['uid'] not in due]) if prepare_remaining_refresh is not None else None if prepare_refresh is None else prepare_refresh(items))
            refresh=[] if prepared is None else list(prepared) if isinstance(prepared,(tuple,list)) else [prepared]
            from els_server.protocol.protocol_codec import encode_event
            for event in [answer]+refresh:encode_event(event)
            db.execute('''CREATE TABLE IF NOT EXISTS expired_item_receipts (
                item_uid INTEGER PRIMARY KEY, owner INTEGER NOT NULL, expired_at INTEGER NOT NULL,
                removed_at INTEGER NOT NULL, item_json TEXT NOT NULL)''')
            for item in items:
                for table in ('equipment_attributes','equipment_durability','equipment_enhancement','equipment_options','equipment_identification','equipment_enhancement_progress', 'item_seals','artifact_equipment_state','equipment_chip_tuning','equipment_reforge_states','equipment_engrave_previews'):
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                        db.execute(f'DELETE FROM {table} WHERE item_uid=?',(item['uid'],))
                forget(db,item['uid'])
                from els_server.storage.item_locks import forget as forget_lock
                forget_lock(db,item['uid'])
                db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item['uid'],owner))
                db.execute('INSERT INTO expired_item_receipts VALUES (?,?,?,?,?)',(item['uid'],owner,item['expires_at'],now,json.dumps(item,sort_keys=True)))
            load_items(db,owner)
            return [answer]+refresh

from els_server.storage.sqlite_timing import write_transaction
