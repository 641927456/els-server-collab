"""Custom period ownership and expiry use the existing registration/expiry writers."""
from contextlib import closing
import sqlite3
from els_server.domain.custom_periods import books,value
from els_server.storage.character_schema import character_uid

TABLE='character_custom_periods'


def exists(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone())


def owned(db,owner,now):
    if not exists(db):return []
    return owned_rows(db.execute('SELECT custom_id,source_template,starts_at,expires_at FROM character_custom_periods WHERE owner=? ORDER BY custom_id',(owner,)),now)


def owned_rows(rows,now):
    result=[]
    for cid,book,start,end in rows:
        rule=books().get(book)
        if rule is None or rule['custom_id']!=cid:raise ValueError('Saved custom period source')
        current=value(cid,start,end)
        if start<=now<=end:result.append((rule,current))
    return result


def register(db,owner,book,start):
    if not db.in_transaction:raise ValueError('Custom period requires registration writer')
    rule=books()[book];end=start+rule['period_seconds'];current=value(rule['custom_id'],start,end)
    db.execute('''CREATE TABLE IF NOT EXISTS character_custom_periods(
        owner INTEGER NOT NULL REFERENCES characters(uid),custom_id INTEGER NOT NULL,
        source_template INTEGER NOT NULL,starts_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,
        PRIMARY KEY(owner,custom_id))''')
    old=db.execute('SELECT expires_at FROM character_custom_periods WHERE owner=?AND custom_id=?',(owner,rule['custom_id'])).fetchone()
    if old is not None and start<=old[0]:raise ValueError('Custom period is already active')
    if old is not None:
        # A cold restore can hide an expired selection before the periodic
        # writer removes it. Renewing ownership must not select it again.
        for table,slot,cid,variant in _expired_selections(db,owner,start):
            if cid==rule['custom_id']:
                db.execute(f'DELETE FROM {table} WHERE owner=?AND slot=?AND custom_id=?',(owner,slot,cid))
    db.execute('''INSERT INTO character_custom_periods VALUES(?,?,?,?,?)
        ON CONFLICT(owner,custom_id)DO UPDATE SET source_template=excluded.source_template,
        starts_at=excluded.starts_at,expires_at=excluded.expires_at''',(owner,rule['custom_id'],book,start,end))
    return current


def _expired_selections(db,owner,now):
    if not exists(db):return []
    expired={cid for cid, in db.execute('SELECT custom_id FROM character_custom_periods WHERE owner=?AND expires_at<?',(owner,now))}
    rows=[]
    from els_server.storage.character_custom import exists as present,SIDE_SELECTED,EXTRA_SELECTED
    if present(db,SIDE_SELECTED):
        rows.extend((SIDE_SELECTED,slot,cid,None)for slot,cid in db.execute('SELECT slot,custom_id FROM character_custom_permanent_selection_slots WHERE owner=?',(owner,))if cid in expired)
    if present(db,EXTRA_SELECTED):
        rows.extend((EXTRA_SELECTED,slot,cid,variant)for slot,cid,variant in db.execute('SELECT slot,custom_id,variant FROM character_custom_permanent_extra_selection WHERE owner=?',(owner,))if cid in expired)
    return rows


def expire(path,owner,*,now,timeout=10):
    owner=character_uid(owner)
    if type(now)is not int or now<0:raise ValueError('Custom expiry clock')
    from els_server.storage.read_scope import snapshot_connection
    with snapshot_connection(path)as db:
        db.execute('BEGIN')
        if not _expired_selections(db,owner,now):return []
    with closing(sqlite3.connect(path,timeout=timeout))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        from els_server.storage.item_actor import require_active_character
        require_active_character(db,owner);rows=_expired_selections(db,owner,now)
        if not rows:return []
        account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
        if account is None:raise ValueError('Custom expiry account identity')
        from els_server.domain.character_custom import canonical,custom_rules
        cleared={slot:canonical(0,variant=variant if variant is not None else custom_rules()[cid]['variant'])for table,slot,cid,variant in rows}
        for table,slot,cid,variant in rows:
            db.execute(f'DELETE FROM {table} WHERE owner=?AND slot=?AND custom_id=?',(owner,slot,cid))
        from els_server.storage.character_custom import actor_selection
        from els_server.storage.titles import equipped
        from els_server.protocol.character_custom_messages import acknowledgement,selected_notice
        from els_server.protocol.protocol_codec import encode_event
        events=[acknowledgement(cleared),selected_notice(owner,equipped(db,owner,now),actor_selection(db,owner,account[0],now))]
        for event in events:encode_event(event)
        return events
