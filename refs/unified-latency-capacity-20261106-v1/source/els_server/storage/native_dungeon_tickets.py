"""Atomic one-ticket admission for two pinned permanent ordinary dungeons."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import closing
from els_server.domain.native_ticket_rules import tickets, enabled
from els_server.storage.item_instances import remove


def _table(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()


def _owner(db, account_id, owner):
    if type(account_id) is not int or account_id < 1 or type(owner) is not int or owner < 1001:
        raise ValueError('Permanent ticket actor identity')
    row = db.execute('''SELECT c.level FROM characters c JOIN character_owners o
        ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?''', (owner, account_id)).fetchone()
    if row is None or row[0] != 99:
        raise ValueError('Permanent ticket role ownership/level')


def selected(db, account_id, owner, dungeon_id, *, now=None):
    allowed = tickets(dungeon_id)
    _owner(db, account_id, owner)
    now = int(time.time()) if now is None else now
    if type(now) is not int or now < 0:
        raise ValueError('Permanent ticket clock')
    # Owned-UID order is the existing event ticket consumer's local selection
    # policy; the client catalog and official pages do not specify an ID order.
    for row in db.execute('''SELECT uid,template,metadata,count,bag_group,slot
        FROM inventory_items WHERE owner=? ORDER BY uid''', (owner,)):
        item = dict(zip(('uid', 'template', 'metadata', 'count', 'group', 'slot'), row))
        if item['template'] not in allowed:
            continue
        if (item['metadata'] != 2 or item['group'] != 4
                or not 1 <= item['uid'] < 2**63 or not 1 <= item['count'] <= 1000
                or not 0 <= item['slot'] < 32768):
            continue
        if _table(db, 'item_expiration'):
            deadline = db.execute('SELECT expires_at FROM item_expiration WHERE item_uid=?', (item['uid'],)).fetchone()
            if deadline and now > deadline[0]:
                continue
            if deadline:
                item['expires_at'] = deadline[0]
        if _table(db, 'item_locks'):
            lock = db.execute('SELECT lock_until FROM item_locks WHERE item_uid=?', (item['uid'],)).fetchone()
            if lock and now <= lock[0]:
                continue
            if lock:
                item['lock_until'] = lock[0]
        if _table(db, 'item_seals'):
            seal = db.execute('SELECT sealed,used FROM item_seals WHERE item_uid=?', (item['uid'],)).fetchone()
            if seal and seal[0]:
                continue
            if seal:
                item.update(sealed=False, seal_used=seal[1])
        return item
    raise ValueError('Owned permanent dungeon ticket required')


def admit(path, account_id, owner, dungeon_id, run_id, request, encode, guard, *, now=None):
    tickets(dungeon_id)
    if not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id:
        raise ValueError('Permanent ticket run identity')
    if not isinstance(request, bytes) or not 1 <= len(request) <= 128:
        raise ValueError('Permanent ticket original request')
    digest = hashlib.sha256(json.dumps([account_id, owner, dungeon_id]).encode() + request).hexdigest()
    with closing(sqlite3.connect(path, timeout=10)) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS native_dungeon_ticket_admissions (
                run_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
                owner INTEGER NOT NULL, dungeon INTEGER NOT NULL,
                ticket_uid INTEGER NOT NULL, consumed INTEGER NOT NULL CHECK(consumed=1),
                response BLOB NOT NULL)''')
            old = db.execute('''SELECT request_sha256,response FROM native_dungeon_ticket_admissions
                WHERE run_id=?''', (run_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('Conflicting permanent ticket retry')
                _owner(db, account_id, owner)
                guard()
                db.commit()
                return old[1]
            if not enabled():
                raise ValueError('Permanent ticket admission disabled')
            guard()
            item = selected(db, account_id, owner, dungeon_id, now=now)
            remaining = item['count'] - 1
            after = {**item, 'count': remaining} if remaining else None
            response = encode(item, after)
            if not isinstance(response, bytes) or len(response) > 1048576:
                raise ValueError('Permanent ticket response encoding')
            guard()
            if remaining:
                if db.execute('''UPDATE inventory_items SET count=? WHERE uid=? AND owner=? AND count=?''',
                        (remaining, item['uid'], owner, item['count'])).rowcount != 1:
                    raise ValueError('Permanent ticket source changed')
            else:
                remove(db, owner, item)
            db.execute('''INSERT INTO native_dungeon_ticket_admissions VALUES (?,?,?,?,?,?,?)''',
                       (run_id, digest, owner, dungeon_id, item['uid'], 1, response))
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise


def admit_group(path, actors, dungeon_id, run_id, request, encode, guard, *, now=None):
    """Select every member before preparing anything; debit all in one writer."""
    tickets(dungeon_id)
    if (not isinstance(actors, tuple) or not 2 <= len(actors) <= 4
            or len({owner for _, owner in actors}) != len(actors)
            or not isinstance(run_id, str) or str(uuid.UUID(run_id)) != run_id
            or not isinstance(request, bytes) or not 1 <= len(request) <= 128):
        raise ValueError('Permanent ticket group identity/request')
    digest = hashlib.sha256(json.dumps([actors, dungeon_id]).encode() + request).hexdigest()
    with closing(sqlite3.connect(path, timeout=10)) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS native_dungeon_ticket_group_admissions (
                run_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
                dungeon INTEGER NOT NULL, members_json TEXT NOT NULL,
                tickets_json TEXT NOT NULL, response BLOB NOT NULL)''')
            old = db.execute('''SELECT request_sha256,response FROM native_dungeon_ticket_group_admissions
                WHERE run_id=?''', (run_id,)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('Conflicting permanent ticket group retry')
                for account_id, owner in actors:
                    _owner(db, account_id, owner)
                db.commit()
                return old[1]
            if not enabled():
                raise ValueError('Permanent ticket admission disabled')
            guard()
            admission_time=int(time.time()) if now is None else now
            chosen = tuple(selected(db, account_id, owner, dungeon_id, now=admission_time)
                           for account_id, owner in actors)
            after = tuple({**item, 'count': item['count']-1} if item['count'] > 1 else None
                          for item in chosen)
            response = encode(chosen, after)
            if not isinstance(response, bytes) or len(response) > 4194304:
                raise ValueError('Permanent ticket group response encoding')
            for (_, owner), item, remaining in zip(actors, chosen, after):
                if remaining is not None:
                    if db.execute('''UPDATE inventory_items SET count=? WHERE uid=? AND owner=? AND count=?''',
                            (remaining['count'], item['uid'], owner, item['count'])).rowcount != 1:
                        raise ValueError('Permanent ticket group source changed')
                else:
                    remove(db, owner, item)
            db.execute('''INSERT INTO native_dungeon_ticket_group_admissions VALUES (?,?,?,?,?,?)''',
                (run_id, digest, dungeon_id, json.dumps(actors),
                 json.dumps([item['uid'] for item in chosen]), response))
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise
