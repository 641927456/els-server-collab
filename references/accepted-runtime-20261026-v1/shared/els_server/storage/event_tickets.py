"""Owned source tickets and atomic, replayable event admission receipts."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import closing
from els_server.domain.event_dungeons import catalog, definition
from els_server.storage.item_instances import remove


def _exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()


def _owner(db, account_id, owner, identity):
    event = definition(identity)
    if (type(account_id) is not int or account_id < 1
            or type(owner) is not int or owner < 1001):
        raise ValueError('Event ticket owner')
    role = db.execute('''SELECT c.level FROM characters c JOIN character_owners o
        ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?''', (owner, account_id)).fetchone()
    if role is None or not event['minimum_level'] <= role[0] <= event['maximum_level']:
        raise ValueError('Event character ownership/level')
    return event


def selected(db, account_id, owner, identity, *, now=None):
    from els_server.domain.gm_events import require_open
    require_open(identity)
    event = _owner(db, account_id, owner, identity)
    now = int(time.time()) if now is None else now
    if type(now) is not int or now < 0:
        raise ValueError('Event admission clock')
    for row in db.execute('''SELECT uid,template,metadata,count,bag_group,slot
            FROM inventory_items WHERE owner=? ORDER BY uid''', (owner,)):
        item = dict(zip(('uid','template','metadata','count','group','slot'), row))
        if item['template'] not in event['tickets']:
            continue
        ticket = catalog()['tickets'][str(item['template'])]
        if (item['metadata'] != ticket['metadata'] or item['group'] != ticket['bag_group']
                or not 1 <= item['uid'] < 2**63
                or type(item['count']) is not int or not event['ticket_count'] <= item['count'] <= 99
                or not 0 <= item['slot'] < 32768):
            continue
        if _exists(db, 'item_expiration'):
            deadline = db.execute('SELECT expires_at FROM item_expiration WHERE item_uid=?', (item['uid'],)).fetchone()
            if deadline and now > deadline[0]:
                continue
            if deadline:item['expires_at'] = deadline[0]
        if _exists(db, 'item_locks'):
            lock = db.execute('SELECT lock_until FROM item_locks WHERE item_uid=?', (item['uid'],)).fetchone()
            if lock and now <= lock[0]:
                continue
            if lock:item['lock_until'] = lock[0]
        if _exists(db, 'item_seals'):
            seal = db.execute('SELECT sealed,used FROM item_seals WHERE item_uid=?', (item['uid'],)).fetchone()
            if seal and seal[0]:
                continue
            if seal:item.update(sealed=False,seal_used=seal[1])
        return item
    raise ValueError('Owned current event ticket required')


def admit(path, account_id, owner, identity, run_id, request, encode, *, now=None):
    if not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id:
        raise ValueError('Event run identity')
    if not isinstance(request, bytes) or not 1 <= len(request) <= 128:
        raise ValueError('Event admission request')
    definition(identity)
    digest = hashlib.sha256(json.dumps([account_id, owner, identity]).encode() + request).hexdigest()
    with closing(sqlite3.connect(path, timeout=10)) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS event_ticket_admissions (
                run_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
                ticket_uid INTEGER NOT NULL, consumed INTEGER NOT NULL,
                response BLOB NOT NULL)''')
            old = db.execute('SELECT request_sha256,response FROM event_ticket_admissions WHERE run_id=?', (run_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('Conflicting event admission retry')
                _owner(db, account_id, owner, identity)
                db.commit()
                return old[1]
            item = selected(db, account_id, owner, identity, now=now)
            count = definition(identity)['ticket_count']
            remaining = item['count'] - count
            after = {**item, 'count': remaining} if remaining else None
            response = encode(item, after)
            if not isinstance(response, bytes) or len(response) > 1048576:
                raise ValueError('Event admission encoding')
            if remaining:
                db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?', (remaining,item['uid'],owner))
            else:
                remove(db, owner, item)
            db.execute('INSERT INTO event_ticket_admissions VALUES (?,?,?,?,?)',
                       (run_id,digest,item['uid'],count,response))
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise
