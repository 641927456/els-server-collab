"""Opt-in committed mailbox snapshot -> original1CE, per connection.

An explicit policy is mandatory; the retail trailingflag/preview limit are
still unverified. No default activation, grant, clock or guessed server IDs.
"""
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from els_server.storage.online_2026_mail_snapshot import snapshot
from els_server.storage.game_mail import _row
from els_server.protocol.mail_notifications_2026 import MailNoticeRow, notice


@dataclass(frozen=True)
class MailNoticePolicy:
    flag: bool
    preview_limit: int

    def __post_init__(self):
        if type(self.flag) is not bool or type(self.preview_limit) is not int or not 0 <= self.preview_limit <= 256:
            raise ValueError('Explicit trailing flag and bounded preview limit required')


class OnlineMailNotice:
    def __init__(self):
        self._accepted = None
        self._busy = False

    def reset(self):
        """Forget only this connection's cache; never clear another mail source."""
        if self._busy:
            raise RuntimeError('Reentrant mail notice reset')
        self._accepted = None

    def synchronize(self, path, *, account, character, now, policy, emit):
        if self._busy:
            raise RuntimeError('Reentrant mail notification')
        if type(policy) is not MailNoticePolicy or not callable(emit):
            raise TypeError('Explicit reviewed mail policy and ordered emitter required')
        resolved = Path(path).resolve()
        self._busy = True
        try:
            # Opening read-only also prevents an accidental new empty player DB.
            with closing(sqlite3.connect(resolved.as_uri()+'?mode=ro', uri=True, timeout=10)) as db:
                db.row_factory = sqlite3.Row
                db.execute('BEGIN')
                try:
                    state = snapshot(db, account=account, character=character, now=now)
                    previews = []
                    for mid in state['visible_unread_ids'][:policy.preview_limit]:
                        row = _row(db, account, mid, character, now=now)
                        item = row.get('item') if row['claimed_at'] is None else None
                        ed = row['ed'] if row['claimed_at'] is None else 0
                        # Exact same template key as the current header encoder.
                        key = item['template'] if item is not None else int(ed > 0)
                        previews.append(MailNoticeRow(row.get('mail_type',5 if item is not None else 0), row['title'],
                                                       row['sender'], key, ed, item))
                    event = notice(unread_counts=state['unread_counts'], rows=previews, flag=policy.flag)
                finally:
                    db.rollback()
            current = (str(resolved), account, character, event.payload)
            if current == self._accepted:
                return 0
            emit(event)
            self._accepted = current  # Synchronous rejection leaves retry intact.
            return 1
        finally:
            self._busy = False
