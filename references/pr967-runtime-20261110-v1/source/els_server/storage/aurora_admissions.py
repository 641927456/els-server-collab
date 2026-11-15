"""One SQLite admission for a solo actor or the original ready party."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone

from els_server.domain.aurora_ticket_rules import enabled, tickets
from els_server.storage.item_instances import remove
from els_server.storage.native_dungeon_tickets import _owner, _table

_BJT = timezone(timedelta(hours=8))


def day_at(moment):
    if type(moment) is not int or not 0 <= moment < 2**40:
        raise ValueError('Aurora admission clock')
    return (datetime.fromtimestamp(moment, _BJT) - timedelta(hours=10)).date().toordinal()


def _chosen(db, owner, allowed, moment):
    # Existing event/permanent ticket consumers choose the lowest owned UID.
    # The original item list does not prescribe a cross-template priority.
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
            if deadline and moment > deadline[0]:
                continue
            if deadline:
                item['expires_at'] = deadline[0]
        if _table(db, 'item_locks'):
            lock = db.execute('SELECT lock_until FROM item_locks WHERE item_uid=?', (item['uid'],)).fetchone()
            if lock and moment <= lock[0]:
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
    raise ValueError('Owned valid Aurora order book required after free entry')


def _free_used(db, owner, dungeon, day):
    if not _table(db, 'aurora_free_admission_counts'):
        return False
    if db.execute('''SELECT 1 FROM aurora_free_admission_counts
        WHERE owner=? AND dungeon=? AND day>?''', (owner, dungeon, day)).fetchone():
        raise ValueError('Aurora saved future day')
    row = db.execute('''SELECT count FROM aurora_free_admission_counts
        WHERE owner=? AND dungeon=? AND day=?''', (owner, dungeon, day)).fetchone()
    if row is not None and (type(row[0]) is not int or row[0] != 1):
        raise ValueError('Aurora saved free count')
    return row is not None


def eligible(path, account, owner, dungeon, *, now=None):
    allowed = tickets(dungeon)
    moment = int(time.time()) if now is None else now
    today = day_at(moment)
    with closing(sqlite3.connect(path)) as db:
        _owner(db, account, owner)
        if not _free_used(db, owner, dungeon, today):
            return True
        _chosen(db, owner, allowed, moment)
        return True


def admit(path, actors, dungeon, run_id, request, encode, guard, *, now=None):
    allowed = tickets(dungeon)
    if (type(actors) is not tuple or not 1 <= len(actors) <= 4
            or any(type(a) is not tuple or len(a) != 2 for a in actors)
            or len({owner for _, owner in actors}) != len(actors)
            or type(run_id) is not str or str(uuid.UUID(run_id)) != run_id
            or type(request) is not bytes or not 1 <= len(request) <= 128):
        raise ValueError('Aurora original run/roster/request')
    digest = hashlib.sha256(json.dumps([actors, dungeon], separators=(',', ':')).encode() + request).hexdigest()
    with closing(sqlite3.connect(path, timeout=10)) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS aurora_free_admission_counts (
                owner INTEGER NOT NULL REFERENCES characters(uid), dungeon INTEGER NOT NULL,
                day INTEGER NOT NULL, count INTEGER NOT NULL CHECK(count=1),
                PRIMARY KEY(owner,dungeon,day))''')
            db.execute('''CREATE TABLE IF NOT EXISTS aurora_admission_receipts (
                run_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, dungeon INTEGER NOT NULL,
                day INTEGER NOT NULL, admitted_at INTEGER NOT NULL,
                members_json TEXT NOT NULL, outcomes_json TEXT NOT NULL, response BLOB NOT NULL)''')
            old = db.execute('''SELECT request_sha256,response FROM aurora_admission_receipts
                WHERE run_id=?''', (run_id,)).fetchone()
            if old is not None:
                if old[0] != digest:
                    raise ValueError('Conflicting Aurora entry replay')
                for account, owner in actors:
                    _owner(db, account, owner)
                db.commit()
                return old[1]
            if not enabled():
                raise ValueError('Aurora admission disabled')
            guard()
            moment = int(time.time()) if now is None else now
            today = day_at(moment)
            plans = []
            for account, owner in actors:
                _owner(db, account, owner)
                if _free_used(db, owner, dungeon, today):
                    item = _chosen(db, owner, allowed, moment)
                    after = {**item, 'count': item['count'] - 1} if item['count'] > 1 else None
                    plans.append((item, after))
                else:
                    plans.append((None, None))
            response = encode(tuple(plans))
            if type(response) is not bytes or not 1 <= len(response) <= 4194304:
                raise ValueError('Aurora original response encoding')
            guard()
            outcomes = []
            for (_, owner), (item, after) in zip(actors, plans):
                if item is None:
                    db.execute('''INSERT INTO aurora_free_admission_counts VALUES (?,?,?,1)''',
                               (owner, dungeon, today))
                    outcomes.append(dict(owner=owner, free=True, ticket_uid=None))
                else:
                    if after is not None:
                        if db.execute('''UPDATE inventory_items SET count=? WHERE uid=? AND owner=? AND count=?''',
                                      (after['count'], item['uid'], owner, item['count'])).rowcount != 1:
                            raise ValueError('Aurora ticket source changed')
                    else:
                        remove(db, owner, item)
                    outcomes.append(dict(owner=owner, free=False, ticket_uid=item['uid']))
            db.execute('''INSERT INTO aurora_admission_receipts VALUES (?,?,?,?,?,?,?,?)''',
                       (run_id, digest, dungeon, today, moment, json.dumps(actors),
                        json.dumps(outcomes, separators=(',', ':')), response))
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise
