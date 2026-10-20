"""Growth progress over the formal account_resonance authority.

Accepts an explicit authoritative level/total pair, never a client-supplied
grant. No automatic initialization, opening, growth-lift policy, point/page
projection or 0x610 emission is performed. Those belong to verified callers.
Savepoints allow the activity binding/reward transaction to own commit.
Old isolated accounts are retained but require an explicit migration before
this adapter can use them. Two cumulative totals are never added or guessed.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import sqlite3
import uuid

from els_server.domain.resonance_2026_curve import CURVE_SHA256, checked_integer


@dataclass(frozen=True)
class ResonanceProgress:
    revision: int
    level: int
    cumulative_experience: int


class ResonanceConflict(ValueError):
    pass


class AccountResonance:
    def __init__(self, connection, curve):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError('Caller-owned SQLite connection required')
        # Integer-normalized [needed,total] checksum of the same pinned catalog.
        # This also rejects a caller constructing a different curve by hand.
        normalized=json.dumps([curve.needed,curve.total],separators=(',',':')).encode()
        if hashlib.sha256(normalized).hexdigest()!='02e68e53e82bd47bcec4d72db35bf69fff236be7e65e8cea9a30f6459050f816':
            raise ValueError('Unverified resonance curve')
        if len(curve.total)!=1000 or len(curve.needed)!=1000 or curve.total[0]!=0 or curve.needed[0]!=0:
            raise ValueError('Incomplete resonance curve')
        if any(type(x) is not int for x in (*curve.total,*curve.needed)) or any(
                curve.total[i]-curve.total[i-1]!=curve.needed[i] or curve.needed[i]<=0
                for i in range(1,1000)):
            raise ValueError('Inconsistent resonance curve')
        self.db=connection
        self.curve=curve

    @contextmanager
    def _transaction(self):
        outer=self.db.in_transaction
        savepoint='resonance_'+uuid.uuid4().hex
        self.db.execute('SAVEPOINT '+savepoint if outer else 'BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('RELEASE '+savepoint) if outer else self.db.commit()
        except BaseException:
            if outer:
                self.db.execute('ROLLBACK TO '+savepoint)
                self.db.execute('RELEASE '+savepoint)
            else:
                self.db.rollback()
            raise

    def initialize(self):
        with self._transaction():
            from els_server.storage.resonance_state import ensure
            ensure(self.db)
            # Retain the old schema for compatibility with table-presence
            # consumers. It is not a second writable ERP authority.
            self.db.execute('''CREATE TABLE IF NOT EXISTS resonance2026_accounts(
                account INTEGER PRIMARY KEY CHECK(account>0),
                revision INTEGER NOT NULL CHECK(revision>0),
                level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 999),
                cumulative_experience INTEGER NOT NULL CHECK(cumulative_experience>=0),
                curve_sha256 TEXT NOT NULL)''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS resonance2026_receipts(
                account INTEGER NOT NULL, operation TEXT NOT NULL,
                request_sha256 TEXT NOT NULL, revision INTEGER NOT NULL,
                level INTEGER NOT NULL, cumulative_experience INTEGER NOT NULL,
                PRIMARY KEY(account,operation))''')

    def _owner(self, account, character):
        for value in (account,character):
            checked_integer(value,'owner identity',1,2**63-1)
        if self.db.execute('''SELECT 1 FROM character_owners o JOIN characters c
                ON c.uid=o.uid WHERE o.account_id=? AND o.uid=?''',
                (account,character)).fetchone() is None:
            raise ValueError('Character does not belong to authenticated account')

    def _validate_pair(self, level, total):
        checked_integer(level,'persisted level',1,999)
        checked_integer(total,'persisted cumulative experience',0,2**63-1)
        if total<self.curve.threshold(level) or (level<999 and total>=self.curve.threshold(level+1)):
            raise ValueError('Level and cumulative experience disagree')
        from els_server.domain.resonance import limit
        if total>limit():
            raise ValueError('Progress exceeds formal account resonance cap')

    def _read(self, account):
        legacy=None
        tables={row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'resonance2026_accounts' in tables and self.db.execute(
                'SELECT 1 FROM resonance2026_accounts WHERE account=?',(account,)).fetchone():
            legacy=self.db.execute('SELECT * FROM resonance2026_accounts WHERE account=?',(account,)).fetchone()
            accepted=self.db.execute('SELECT legacy_sha256 FROM resonance2026_canonical_migrations WHERE account=?',
                (account,)).fetchone() if 'resonance2026_canonical_migrations' in tables else None
            if accepted!=(self._legacy_digest(legacy),):
                raise ResonanceConflict('Legacy isolated resonance requires explicit checked migration')
        if 'account_resonance' not in tables:return None
        row=self.db.execute('SELECT enabled,experience,revision FROM account_resonance WHERE account_id=?',(account,)).fetchone()
        if row is None:return None
        enabled,total,revision=row
        if legacy is not None and (not enabled or total<legacy[3]):
            raise ResonanceConflict('Formal authority no longer covers adopted legacy state')
        if type(enabled) is not int or enabled not in (0,1):
            raise ValueError('Invalid formal resonance enable state')
        checked_integer(total,'formal cumulative experience',0,2**63-1)
        checked_integer(revision,'formal revision',0,2**63-1)
        if not enabled:
            if total:raise ValueError('Disabled formal resonance has experience')
            return None
        from els_server.domain.resonance import level
        current_level=level(total)
        self._validate_pair(current_level,total)
        return ResonanceProgress(revision,current_level,total)

    @staticmethod
    def _legacy_digest(row):
        return hashlib.sha256(json.dumps(list(row),separators=(',',':')).encode()).hexdigest()

    def migrate_dominated_legacy(self, *, account, character):
        """Adopt history only when the formal authority already covers it.

        No XP, revision, pages, points or original receipts are changed. Lower,
        unopened or inconsistent formal state needs separate reconciliation.
        A later writer changing the retired balance invalidates this adoption.
        """
        if not self.db.in_transaction:raise ValueError('Caller-owned migration required')
        self._owner(account,character)
        old=self.db.execute('SELECT * FROM resonance2026_accounts WHERE account=?',(account,)).fetchone()
        if old is None:return False
        if len(old)!=5 or old[0]!=account or old[4]!=CURVE_SHA256:
            raise ResonanceConflict('Legacy curve or account differs')
        checked_integer(old[1],'legacy revision',1,2**63-1)
        self._validate_pair(old[2],old[3])
        from els_server.storage.resonance_state import snapshot
        current=snapshot(self.db,character,account)
        if not current['enabled'] or current['experience']<old[3]:
            raise ResonanceConflict('Formal balance does not cover legacy progress; no automatic grant')
        self.db.execute('''CREATE TABLE IF NOT EXISTS resonance2026_canonical_migrations(
            account INTEGER PRIMARY KEY,legacy_sha256 TEXT NOT NULL,
            canonical_experience INTEGER NOT NULL,canonical_revision INTEGER NOT NULL,
            policy TEXT NOT NULL)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS resonance2026_legacy_receipt_audit(
            account INTEGER NOT NULL,operation TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,
            PRIMARY KEY(account,operation))''')
        digest=self._legacy_digest(old)
        prior=self.db.execute('SELECT legacy_sha256 FROM resonance2026_canonical_migrations WHERE account=?',(account,)).fetchone()
        if prior is not None:
            if prior!=(digest,):raise ResonanceConflict('Retired legacy account changed')
            return False
        for row in self.db.execute('SELECT operation,request_sha256,revision,level,cumulative_experience FROM resonance2026_receipts WHERE account=?',(account,)).fetchall():
            checked_integer(row[2],'legacy receipt revision',1,old[1])
            self._validate_pair(row[3],row[4])
            if row[4]>old[3]:raise ResonanceConflict('Legacy receipt exceeds its account')
            self.db.execute('INSERT INTO resonance2026_legacy_receipt_audit VALUES (?,?,?)',
                (account,row[0],self._legacy_digest(row)))
        self.db.execute('INSERT INTO resonance2026_canonical_migrations VALUES (?,?,?,?,?)',
            (account,digest,current['experience'],current['revision'],'canonical-dominates-legacy-no-sum-v1'))
        return True

    def snapshot(self, *, account, character):
        with self._transaction():
            self._owner(account,character)
            return self._read(account)

    def record(self, *, account, character, operation, expected_revision, level, cumulative_experience):
        """CAS write of already determined authoritative progress.

        Revision zero requires no prior row. An identical operation replays its
        original committed result, without reverting newer state. If called
        within a transaction, the result is provisional until that caller commits.
        This method is not exposed to a network request or a GM grant endpoint.
        """
        if type(operation) is not str or not 1<=len(operation)<=160:
            raise ValueError('Stable authoritative operation identity required')
        checked_integer(expected_revision,'expected revision',0,2**63-2)
        self._validate_pair(level,cumulative_experience)
        digest=hashlib.sha256(json.dumps([account,character,expected_revision,level,cumulative_experience,CURVE_SHA256],separators=(',',':')).encode()).hexdigest()
        with self._transaction():
            self._owner(account,character)
            current=self._read(account)
            old=self.db.execute('''SELECT request_sha256,revision,level,cumulative_experience
                    FROM resonance2026_receipts WHERE account=? AND operation=?''',(account,operation)).fetchone()
            if old is not None:
                if old[0]!=digest:
                    raise ResonanceConflict('Operation identity was reused for different progress')
                tables={r[0]for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                audit=self.db.execute('SELECT receipt_sha256 FROM resonance2026_legacy_receipt_audit WHERE account=? AND operation=?',
                    (account,operation)).fetchone() if 'resonance2026_legacy_receipt_audit' in tables else None
                migrated=audit==(self._legacy_digest((operation,*old)),)
                if audit is not None and not migrated:raise ResonanceConflict('Retired legacy receipt changed')
                if current is None or (not migrated and current.revision<old[1]) or current.cumulative_experience<old[3]:
                    raise ResonanceConflict('Receipt has no committed progress')
                self._validate_pair(old[2],old[3])
                return ResonanceProgress(*old[1:])
            if (current.revision if current else 0)!=expected_revision:
                raise ResonanceConflict('Stale account resonance revision')
            if current is None and self.db.execute('SELECT 1 FROM account_resonance WHERE account_id=?',(account,)).fetchone():
                raise ResonanceConflict('Existing disabled formal state requires explicit opening policy')
            if current and (level<current.level or cumulative_experience<current.cumulative_experience):
                raise ResonanceConflict('Progress cannot move backwards')
            result=ResonanceProgress(expected_revision+1,level,cumulative_experience)
            self.db.execute('''INSERT INTO account_resonance VALUES (?,1,?,?)
                ON CONFLICT(account_id) DO UPDATE SET experience=excluded.experience,
                revision=excluded.revision''',
                (account,cumulative_experience,result.revision))
            self.db.execute('INSERT INTO resonance2026_receipts VALUES (?,?,?,?,?,?)',
                (account,operation,digest,result.revision,level,cumulative_experience))
            return result
