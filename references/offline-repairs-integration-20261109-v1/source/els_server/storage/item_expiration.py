"""UID-owned deadlines; grants and removal share the existing inventory transaction."""
import json,sqlite3,time
from contextlib import closing
from els_server.domain.item_expiration import validate
from els_server.storage.character_schema import character_uid


def exists(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_expiration'").fetchone())


def attach(db,items,owner):
    if exists(db):
        owned={i['uid']:i for i in items}
        for uid,deadline in db.execute('''SELECT e.item_uid,e.expires_at FROM item_expiration e
            JOIN inventory_items i ON i.uid=e.item_uid WHERE i.owner=?''',(owner,)):
            if uid in owned:owned[uid]['expires_at']=validate(deadline)
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='item_activation_periods'").fetchone():
        from els_server.domain.item_expiration import activation_period
        owned={i['uid']:i for i in items}
        for uid,seconds in db.execute('''SELECT p.item_uid,p.seconds FROM item_activation_periods p
            JOIN inventory_items i ON i.uid=p.item_uid WHERE i.owner=?''',(owner,)):
            if uid in owned:owned[uid]['activation_seconds']=activation_period(seconds)
    from els_server.domain.boosting_2026_item_policy import item_deadline
    for item in items:
        deadline=item_deadline(item)
        if deadline is not None:item['expires_at']=validate(deadline)
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
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='item_activation_periods'").fetchone():
        db.execute('DELETE FROM item_activation_periods WHERE item_uid=?',(item_uid,))


def assign_activation(db,owner,item_uid,seconds):
    from els_server.domain.item_expiration import activation_period
    seconds=activation_period(seconds);owner=character_uid(owner)
    if not db.in_transaction or db.execute('SELECT owner FROM inventory_items WHERE uid=?',(item_uid,)).fetchone()!=(owner,):
        raise ValueError('First-use period requires the owned item writer')
    if exists(db)and db.execute('SELECT 1 FROM item_expiration WHERE item_uid=?',(item_uid,)).fetchone():
        raise ValueError('First-use item already has a deadline')
    db.execute('''CREATE TABLE IF NOT EXISTS item_activation_periods(
        item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,
        seconds INTEGER NOT NULL)''')
    db.execute('INSERT INTO item_activation_periods VALUES(?,?)',(item_uid,seconds))


def activate(db,owner,item,*,now=None):
    if 'activation_seconds'not in item:return item
    from els_server.domain.item_expiration import activation_period
    seconds=activation_period(item['activation_seconds'])
    if not db.in_transaction or db.execute('SELECT seconds FROM item_activation_periods WHERE item_uid=?',(item['uid'],)).fetchone()!=(seconds,):
        raise ValueError('First-use period source differs from current instance')
    when=int(time.time())if now is None else now
    if type(when)is not int:raise ValueError('First-use period clock')
    deadline=validate(when+seconds);assign(db,owner,item['uid'],deadline)
    db.execute('DELETE FROM item_activation_periods WHERE item_uid=?',(item['uid'],))
    current=dict(item);del current['activation_seconds'];current['expires_at']=deadline
    return current


def remove_due(path,owner,*,now=None,prepare_refresh=None,prepare_remaining_refresh=None,timeout=10):
    from els_server.storage.inventory_state import load_items
    from els_server.protocol.expiration_messages import notice
    owner=character_uid(owner);now=int(time.time()) if now is None else now
    if type(now) is not int or now<0:raise ValueError('Invalid expiration clock')
    from els_server.storage.read_scope import snapshot_connection
    from els_server.domain.boosting_2026_item_policy import EVENT_ITEMS,deadline
    def due_ids(db):
        due=set()
        if exists(db):
            due.update(r[0] for r in db.execute('''SELECT e.item_uid FROM item_expiration e
                JOIN inventory_items i ON i.uid=e.item_uid WHERE i.owner=? AND e.expires_at<?''',(owner,now)))
        # Legacy event rows predate explicit instance deadlines. Read them in
        # the same expiry transaction; never rewrite immutable old receipts.
        if now>deadline():
            due.update(uid for uid,t in db.execute('SELECT uid,template FROM inventory_items WHERE owner=?',(owner,))if t in EVENT_ITEMS)
        return due
    with snapshot_connection(path) as probe:
        probe.execute('BEGIN')
        if not due_ids(probe):return []
    # A positive preview never supplies authority: re-read current deadlines
    # and exact owned inventory after taking the unchanged writer lock.
    with closing(sqlite3.connect(path,timeout=timeout)) as db:
        with write_transaction(db):
            due=due_ids(db)
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
            from els_server.storage.item_instances import remove
            for item in items:
                remove(db,owner,item)
                db.execute('INSERT INTO expired_item_receipts VALUES (?,?,?,?,?)',(item['uid'],owner,item['expires_at'],now,json.dumps(item,sort_keys=True)))
            load_items(db,owner)
            return [answer]+refresh

from els_server.storage.sqlite_timing import write_transaction
