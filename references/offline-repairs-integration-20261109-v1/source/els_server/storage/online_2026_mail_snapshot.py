"""Read-only unread state using the inbox's character scope and folder route.

The caller owns a read transaction. No expiry maintenance, DDL or issuance.
"""
import sqlite3
from els_server.storage.game_mail import MailError, _owner
from els_server.storage.player_mail import visible_sql, folder_sql
from els_server.storage.online_title_mail_scope import exists


def snapshot(db, *, account, character, now):
    if not isinstance(db, sqlite3.Connection) or not db.in_transaction:
        raise RuntimeError('Caller-owned read transaction required')
    if type(now) is not int or not 0 < now < 2**63:
        raise MailError('Invalid mail snapshot time')
    _owner(db, account, character)
    condition = ('account_id=? AND deleted_at IS NULL AND expires_at>? '
                 'AND read_at IS NULL AND ' + visible_sql(db))
    args = (account, now, character)
    rows = db.execute('SELECT id,(' + folder_sql(db) + ') FROM game_mail WHERE '
                      + condition + ' ORDER BY id DESC', args).fetchall()
    unread = tuple(row[0] for row in rows)
    if len(unread) >= 2**31:
        raise MailError('Unread total exceeds original signed client counter')
    counts = dict.fromkeys(range(5), 0)
    for _, folder in rows:
        counts[folder] += 1
    activity = ()
    if exists(db):
        activity = tuple(row[0] for row in db.execute(
            'SELECT id FROM game_mail WHERE ' + condition + ''' AND EXISTS (
                SELECT 1 FROM online2026_mail_scope e WHERE e.mail_id=game_mail.id
                AND e.account_id=game_mail.account_id AND e.recipient_uid=?
                AND e.deadline=game_mail.expires_at) ORDER BY id DESC''',
            args + (character,)))
    return dict(unread_counts=counts,
                visible_unread_ids=unread,activity_unread_ids=activity,
                routing='existing_local_mail_flow_folders')
