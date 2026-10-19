"""Selected CN2026 coexistence title: character/week observed-time ledger.

Internal candidate only. The caller must authenticate the character, admit the
session/scene, supply observed integer-second spans, and own the transaction.
No clock, schedule guess, event code, mail, reward item or activation lives here.
Explicit half-open period boundaries must be supplied with provenance; local
test periods are labelled as such. Condition met is NOT a delivery entitlement.
"""
import contextlib
import hashlib
import sqlite3
import uuid

SELECTION_SHA256 = '077035ffbeecf791a6473580ffc1deaf009f41939dd0664cdd97a4ca9126cbdb'


def _text(value):
    if type(value) is not str or not value.strip() or len(value) > 500:
        raise ValueError('Nonempty bounded identifier/provenance required')
    return value


def _integer(value, minimum=0):
    if type(value) is not int or not minimum <= value < 2**63:
        raise ValueError('Invalid integer')
    return value


class OnlineTitleProgress:
    def __init__(self, connection, selection_bytes, *, campaign):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError('Caller-owned SQLite connection required')
        if hashlib.sha256(selection_bytes).hexdigest() != SELECTION_SHA256:
            raise ValueError('Selected official rule evidence changed')
        self.db = connection
        self.campaign = _text(campaign)  # Internal identity, never a client code.

    @contextlib.contextmanager
    def _atomic(self):
        if not self.db.in_transaction:
            raise RuntimeError('Caller transaction required')
        name = 'online_title_' + uuid.uuid4().hex
        self.db.execute('SAVEPOINT ' + name)
        try:
            yield
        except BaseException:
            self.db.execute('ROLLBACK TO ' + name)
            self.db.execute('RELEASE ' + name)
            raise
        else:
            self.db.execute('RELEASE ' + name)

    def initialize(self):
        with self._atomic():
            for sql in (
                '''CREATE TABLE IF NOT EXISTS online2026_campaigns(
                   campaign TEXT PRIMARY KEY, definition_sha256 TEXT NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS online2026_periods(
                   campaign TEXT NOT NULL, week INTEGER NOT NULL CHECK(week BETWEEN 1 AND 4),
                   starts INTEGER NOT NULL, ends INTEGER NOT NULL CHECK(ends>starts),
                   purpose TEXT NOT NULL, provenance TEXT NOT NULL,
                   PRIMARY KEY(campaign,week))''',
                '''CREATE TABLE IF NOT EXISTS online2026_spans(
                   campaign TEXT NOT NULL, account INTEGER NOT NULL,
                   character INTEGER NOT NULL, operation TEXT NOT NULL,
                   week INTEGER NOT NULL, starts INTEGER NOT NULL,
                   ends INTEGER NOT NULL CHECK(ends>starts), level INTEGER NOT NULL,
                   PRIMARY KEY(campaign,account,operation))''',
                '''CREATE INDEX IF NOT EXISTS online2026_character_spans
                   ON online2026_spans(campaign,character,week,starts,ends)'''):
                self.db.execute(sql)
            self.db.execute('INSERT OR IGNORE INTO online2026_campaigns VALUES (?,?)',
                            (self.campaign, SELECTION_SHA256))
            self._definition()

    def _definition(self):
        row = self.db.execute('SELECT definition_sha256 FROM online2026_campaigns WHERE campaign=?',
                              (self.campaign,)).fetchone()
        if row is None or row[0] != SELECTION_SHA256:
            raise ValueError('Unregistered or changed definition')

    def _owner(self, account, character):
        _integer(account, 1); _integer(character, 1)
        row = self.db.execute('''SELECT c.level FROM characters c
            JOIN character_owners o ON o.uid=c.uid WHERE o.account_id=? AND c.uid=?''',
            (account, character)).fetchone()
        if row is None:
            raise ValueError('Character is not owned by this account')
        return row[0]

    def _period(self, week):
        _integer(week, 1)
        if week > 4:
            raise ValueError('Only four selected weekly windows')
        self._definition()
        row = self.db.execute('SELECT starts,ends FROM online2026_periods WHERE campaign=? AND week=?',
                              (self.campaign, week)).fetchone()
        if row is None:
            raise ValueError('Explicit period boundaries missing')
        return tuple(row)

    def register_period(self, *, week, starts, ends, purpose, provenance):
        """Bounds are explicit [start,end), never inferred from maintenance text.

        purpose is cn_2026_historical or explicit_local_test. Supplying a historical
        label does not verify evidence: the integrating caller owes that check.
        """
        _integer(week, 1); _integer(starts); _integer(ends); _text(provenance)
        if week > 4 or starts >= ends or purpose not in ('cn_2026_historical', 'explicit_local_test'):
            raise ValueError('Invalid explicit period')
        with self._atomic():
            self._definition()
            rows = self.db.execute('SELECT week,starts,ends,purpose,provenance FROM online2026_periods WHERE campaign=?',
                                   (self.campaign,)).fetchall()
            for w, s, e, p, evidence in rows:
                if p != purpose:
                    raise ValueError('Test and historical periods cannot share a campaign')
                if w == week:
                    if (s, e, p, evidence) != (starts, ends, purpose, provenance):
                        raise ValueError('Registered period is immutable')
                    return
                if (w < week and e > starts) or (w > week and s < ends):
                    raise ValueError('Weekly windows overlap or run backwards')
            self.db.execute('INSERT INTO online2026_periods VALUES (?,?,?,?,?,?)',
                            (self.campaign, week, starts, ends, purpose, provenance))

    def snapshot(self, *, account, character, week):
        self._owner(account, character); self._period(week)
        rows = self.db.execute('''SELECT starts,ends FROM online2026_spans
            WHERE campaign=? AND character=? AND account=? AND week=? ORDER BY starts,ends''',
            (self.campaign, character, account, week)).fetchall()
        seconds = 0
        right = None
        for start, end in rows:
            seconds += end - start if right is None else max(0, end - max(start, right))
            right = end if right is None else max(right, end)
        return dict(character=character, week=week, observed_online_seconds=seconds,
                    remaining_seconds=max(0, 1800-seconds), condition_met=seconds >= 1800,
                    reward_status='pending_original_mapping', reward_granted=False)

    def record_span(self, *, account, character, week, operation, starts, ends):
        """Record an already admitted live span, not wall time since last login.

        Retry returns CURRENT progress, without adding a receipt/time again.
        Crossing a boundary is rejected; caller must split observed spans and
        exclude maintenance gaps. Receipt key is campaign/account/operation.
        """
        _text(operation); _integer(starts); _integer(ends)
        if ends <= starts:
            raise ValueError('Empty or reversed span')
        with self._atomic():
            level = self._owner(account, character)
            lo, hi = self._period(week)
            if starts < lo or ends > hi:
                raise ValueError('Span crosses explicit period bounds')
            old = self.db.execute('''SELECT character,week,starts,ends FROM online2026_spans
                WHERE campaign=? AND account=? AND operation=?''',
                (self.campaign, account, operation)).fetchone()
            if old is not None:
                if tuple(old) != (character, week, starts, ends):
                    raise ValueError('Operation identity conflicts with stored span')
            else:
                if type(level) is not int or level < 10:
                    raise ValueError('Selected activity requires level10')
                self.db.execute('INSERT INTO online2026_spans VALUES (?,?,?,?,?,?,?,?)',
                                (self.campaign, account, character, operation, week, starts, ends, level))
            return self.snapshot(account=account, character=character, week=week)
