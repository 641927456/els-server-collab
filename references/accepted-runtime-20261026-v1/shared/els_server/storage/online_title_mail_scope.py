"""Recipient/expiry guard for a future verified2026 title-mail producer.

This module does NOT create mail/items, choose event IDs, or award progress.
The producer remains absent. Binding must occur in the same transaction as
issuance; a bound title token expires with its event letter, never returns.
"""
import json
from els_server.storage.game_mail import MailError, _owner


def exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='online2026_mail_scope'").fetchone() is not None


def recipient(db, mail_id):
    if not exists(db):
        return None
    row=db.execute('SELECT recipient_uid FROM online2026_mail_scope WHERE mail_id=?',(mail_id,)).fetchone()
    return row[0] if row else None


def bind(db, *, mail_id, account, character, deadline):
    """Bind an already prepared original723809x1 escrow; never mint a reward."""
    if not db.in_transaction:
        raise MailError('Title mail binding requires issuance transaction')
    if any(type(v) is not int or v < 1 for v in (mail_id,account,character,deadline)):
        raise MailError('Invalid title mail scope')
    _owner(db,account,character)
    row=db.execute('SELECT account_id,ed,expires_at,claimed_at,deleted_at FROM game_mail WHERE id=?',(mail_id,)).fetchone()
    if row is None or tuple(row)!=(account,0,deadline,None,None):
        raise MailError('Unclaimed event letter with exact global deadline required')
    if db.execute('SELECT 1 FROM player_mail_meta WHERE mail_id=?',(mail_id,)).fetchone():
        raise MailError('Ordinary player-mail return metadata is not event-mail scope')
    item=db.execute('''SELECT item_json,expires_at,claimed_at,moved_to,expired_at
        FROM player_mail_items WHERE mail_id=?''',(mail_id,)).fetchone()
    if item is None or tuple(item)[1:]!=(deadline,None,None,None):
        raise MailError('Event attachment deadline/scope missing')
    value=json.loads(item[0])
    if value.get('template')!=723809 or value.get('count')!=1 or value.get('expires_at')!=deadline:
        raise MailError('Exact verified title token required')
    db.execute('''CREATE TABLE IF NOT EXISTS online2026_mail_scope(
        mail_id INTEGER PRIMARY KEY REFERENCES game_mail(id),
        account_id INTEGER NOT NULL, recipient_uid INTEGER NOT NULL,
        deadline INTEGER NOT NULL)''')
    old=db.execute('SELECT account_id,recipient_uid,deadline FROM online2026_mail_scope WHERE mail_id=?',(mail_id,)).fetchone()
    if old is not None and tuple(old)!=(account,character,deadline):
        raise MailError('Title mail recipient/deadline cannot change')
    db.execute('INSERT OR IGNORE INTO online2026_mail_scope VALUES (?,?,?,?)',(mail_id,account,character,deadline))


def retire_due(db, now, *, mail_ids=None):
    if not db.in_transaction:
        raise MailError('Title mail expiry requires transaction')
    if not exists(db):
        return 0
    args=[now];clause=''
    if mail_ids is not None:
        from els_server.storage.game_mail import _ids
        _ids(mail_ids)
        clause=' AND g.id IN ('+','.join('?' for _ in mail_ids)+')';args.extend(mail_ids)
    rows=db.execute('''SELECT g.id FROM game_mail g JOIN online2026_mail_scope e ON e.mail_id=g.id
        WHERE g.deleted_at IS NULL AND e.deadline<=?'''+clause+' ORDER BY g.id LIMIT 100',args).fetchall()
    for (mail_id,) in rows:
        db.execute('UPDATE game_mail SET deleted_at=? WHERE id=?',(now,mail_id))
        db.execute('''UPDATE player_mail_items SET expired_at=COALESCE(expired_at,?)
            WHERE mail_id=? AND claimed_at IS NULL AND moved_to IS NULL''',(now,mail_id))
    return len(rows)


def has_due(db, now):
    return exists(db) and db.execute('''SELECT 1 FROM game_mail g JOIN online2026_mail_scope e
        ON e.mail_id=g.id WHERE g.deleted_at IS NULL AND e.deadline<=? LIMIT 1''',(now,)).fetchone() is not None
