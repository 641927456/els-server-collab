"""Character-owned blacklist and read-only mailbox status snapshots.

Administrative mail bypasses the player blacklist. No sender transfers are
enabled here. Changes and their persistent retry receipts are atomic.
"""
from contextlib import closing
import hashlib
import json
import sqlite3
import time


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS mail_blacklist (
        owner INTEGER NOT NULL, target INTEGER NOT NULL, name TEXT NOT NULL,
        created_at INTEGER NOT NULL, PRIMARY KEY(owner,target), CHECK(owner!=target))''')
    db.execute('''CREATE TABLE IF NOT EXISTS mail_blacklist_receipts (
        operation TEXT PRIMARY KEY, account_id INTEGER NOT NULL,
        owner INTEGER NOT NULL, digest TEXT NOT NULL, target INTEGER NOT NULL,
        name TEXT NOT NULL, added INTEGER NOT NULL CHECK(added IN (0,1)),
        created_at INTEGER NOT NULL)''')


def _rows(db, uid):
    return [dict(uid=r[0], name=r[1]) for r in db.execute(
        '''SELECT b.target,COALESCE(c.name,b.name) FROM mail_blacklist b
        LEFT JOIN characters c ON c.uid=b.target WHERE b.owner=?
        ORDER BY b.created_at,b.target''', (uid,))]


def blacklist(path, account, uid):
    from els_server.storage.game_mail import _owner
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.execute('BEGIN'); _owner(db, account, uid)
        return _rows(db, uid)


def change(path, account, uid, target, *, added, operation, encode, now=None):
    from els_server.storage.game_mail import MailError, _owner
    from els_server.storage.characters import validate_name
    if type(added) is not bool or not isinstance(operation, str) or not 1 <= len(operation) <= 160:
        raise MailError('Invalid blacklist operation')
    if added:
        validate_name(target)
    elif type(target) is not int or not 1001 <= target < 2**63:
        raise MailError('Invalid blacklist target')
    digest = hashlib.sha256(json.dumps([added,target], ensure_ascii=True).encode()).hexdigest()
    now = int(time.time()) if now is None else now
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('BEGIN IMMEDIATE'); _owner(db, account, uid)
        old = db.execute('''SELECT account_id,owner,digest,target,name FROM
            mail_blacklist_receipts WHERE operation=?''', (operation,)).fetchone()
        if old:
            if old[:3] != (account,uid,digest):
                raise MailError('Blacklist retry conflicts with original request')
            target_uid, name = old[3:]
        else:
            if added:
                row = db.execute('''SELECT c.uid,c.name FROM characters c
                    JOIN character_owners o ON o.uid=c.uid WHERE c.name_key=?''',
                    (target.casefold(),)).fetchone()
            else:
                row = db.execute('''SELECT b.target,COALESCE(c.name,b.name)
                    FROM mail_blacklist b LEFT JOIN characters c ON c.uid=b.target
                    WHERE b.owner=? AND b.target=?''', (uid,target)).fetchone()
                if row is None:
                    row = db.execute('SELECT uid,name FROM characters WHERE uid=?', (target,)).fetchone()
            if row is None or row[0] == uid:
                raise MailError('Blacklist character not found or self selected')
            target_uid, name = row
            if added:
                # Explicit server storage bound, not a claimed retail limit.
                if (db.execute('SELECT count(*) FROM mail_blacklist WHERE owner=?',(uid,)).fetchone()[0] >= 1000
                        and not db.execute('SELECT 1 FROM mail_blacklist WHERE owner=? AND target=?',(uid,target_uid)).fetchone()):
                    raise MailError('Blacklist storage bound')
                db.execute('INSERT OR IGNORE INTO mail_blacklist VALUES (?,?,?,?)',
                           (uid,target_uid,name,now))
            else:
                db.execute('DELETE FROM mail_blacklist WHERE owner=? AND target=?', (uid,target_uid))
            db.execute('INSERT INTO mail_blacklist_receipts VALUES (?,?,?,?,?,?,?,?)',
                       (operation,account,uid,digest,target_uid,name,int(added),now))
        current = bool(db.execute('SELECT 1 FROM mail_blacklist WHERE owner=? AND target=?',
                                  (uid,target_uid)).fetchone())
        # A late retry must not recreate a block removed by a newer operation.
        # Encode before commit so an encoder failure also rolls back the write.
        return encode(dict(uid=target_uid,name=name), 0 if current == added else 1, _rows(db,uid))


def status(path, account, uid, *, now=None):
    from els_server.storage.game_mail import _owner
    from els_server.storage.player_mail import visible_sql
    now = int(time.time()) if now is None else now
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.execute('BEGIN'); _owner(db, account, uid)
        count, unread, last = db.execute('''SELECT count(*),
            COALESCE(sum(read_at IS NULL),0),COALESCE(max(id),0)
            FROM game_mail WHERE account_id=? AND deleted_at IS NULL AND expires_at>? AND '''+visible_sql(db),
            (account,now,uid)).fetchone()
        return count, unread, last


