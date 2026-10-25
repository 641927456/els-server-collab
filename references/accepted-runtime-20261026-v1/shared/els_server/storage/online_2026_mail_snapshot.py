"""Read-only character-visible unread state for the existing local mail route.

The current mail_flow exposes every implemented letter in folder0. Preserve
that routing here, including ordinary/GM mail; do not pretend that a new
activity-only count is the complete mailbox snapshot. Reclassification of
ordinary letters requires a coordinated change to the existing list route.
The caller owns a read transaction. No expiry maintenance, DDL or issuance.
"""
import sqlite3
from els_server.storage.game_mail import MailError, _owner
from els_server.storage.player_mail import visible_sql
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
    unread = tuple(row[0] for row in db.execute(
        'SELECT id FROM game_mail WHERE ' + condition + ' ORDER BY id DESC', args))
    if len(unread) >= 2**31:
        raise MailError('Unread total exceeds original signed client counter')
    activity = ()
    if exists(db):
        activity = tuple(row[0] for row in db.execute(
            'SELECT id FROM game_mail WHERE ' + condition + ''' AND EXISTS (
                SELECT 1 FROM online2026_mail_scope e WHERE e.mail_id=game_mail.id
                AND e.account_id=game_mail.account_id AND e.recipient_uid=?
                AND e.deadline=game_mail.expires_at) ORDER BY id DESC''',
            args + (character,)))
    return dict(unread_counts={0:len(unread),1:0,2:0,3:0,4:0},
                visible_unread_ids=unread,activity_unread_ids=activity,
                routing='existing_local_mail_flow_folder0')
