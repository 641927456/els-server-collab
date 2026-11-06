"""One immutable account binding for selected CN combat boost 678.

Storage component only: record_binding requires its caller's transaction so
binding, resonance change and rewards can commit or roll back together. It is
not an implemented join handler. Callers must first verify activity scheduling,
original participation reward8173, resonance-lift policy and client conditions.
No default grant, schedule, success packet or account resonance is invented.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import sqlite3
import uuid

from els_server.domain.boosting_2026 import BoostingDefinition, SOURCE_SHA256


def integer(value, name, low=1):
    if type(value) is not int or not low <= value < 2**63:
        raise ValueError('Invalid combat boost '+name)
    return value


class ParticipationConflict(ValueError):
    pass


@dataclass(frozen=True)
class Participation:
    character_uid: int
    joined_at: int
    operation: str


class BoostingParticipation:
    def __init__(self, connection, original_definition):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError('Caller-owned SQLite connection required')
        self.definition=BoostingDefinition.from_original(original_definition)
        self.db=connection

    @contextmanager
    def _savepoint(self):
        name='boost678_'+uuid.uuid4().hex
        self.db.execute('SAVEPOINT '+name)
        try:
            yield
            self.db.execute('RELEASE '+name)
        except BaseException:
            self.db.execute('ROLLBACK TO '+name)
            self.db.execute('RELEASE '+name)
            raise

    def initialize(self):
        with self._savepoint():
            self.db.execute('''CREATE TABLE IF NOT EXISTS boosting2026_participation(
                account INTEGER PRIMARY KEY CHECK(account>0),
                campaign INTEGER NOT NULL CHECK(campaign=678),
                character INTEGER NOT NULL CHECK(character>0),
                joined_at INTEGER NOT NULL CHECK(joined_at>=0),
                operation TEXT NOT NULL,
                definition_sha256 TEXT NOT NULL,
                request_sha256 TEXT NOT NULL)''')

    def _owner_level(self, account, character):
        integer(account,'account');integer(character,'character')
        row=self.db.execute('''SELECT c.level FROM characters c
            JOIN character_owners o ON o.uid=c.uid
            WHERE o.account_id=? AND c.uid=?''',(account,character)).fetchone()
        if row is None:
            raise ValueError('Character does not belong to authenticated account')
        return integer(row[0],'stored character level')

    def _digest(self, account, character, operation):
        return hashlib.sha256(json.dumps([account,678,character,operation,SOURCE_SHA256],
                                        separators=(',',':')).encode()).hexdigest()

    def _read(self, account):
        row=self.db.execute('''SELECT campaign,character,joined_at,operation,
            definition_sha256,request_sha256 FROM boosting2026_participation
            WHERE account=?''',(account,)).fetchone()
        if row is None:
            return None
        campaign,character,joined_at,operation,source,digest=row
        integer(character,'stored binding');integer(joined_at,'stored join time',0)
        if type(operation) is not str or not 1<=len(operation)<=160:
            raise ParticipationConflict('Corrupt participation operation')
        if campaign!=678 or source!=SOURCE_SHA256 or digest!=self._digest(account,character,operation):
            raise ParticipationConflict('Stored participation definition or receipt differs')
        return Participation(character,joined_at,operation)

    def snapshot(self, *, account, character):
        """Any currently owned character may read its account's bound UID.

        No missing bound-character row is silently deleted or treated as a
        fresh campaign. Such recovery requires separate verified rules.
        """
        with self._savepoint():
            self._owner_level(account,character)
            return self._read(account)

    def record_binding(self, *, account, character, operation, joined_at):
        """Record a qualified participation inside an already open join TX.

        The timestamp is server observation metadata, not part of request
        identity: an identical retry returns its original timestamp. Other
        operation IDs or characters cannot replace an existing binding.
        The caller must not report success until its outer transaction commits.
        """
        if not self.db.in_transaction:
            raise ValueError('Participation requires caller-owned join transaction')
        if type(operation) is not str or not 1<=len(operation)<=160:
            raise ValueError('Stable participation operation identity required')
        integer(joined_at,'join time',0)
        with self._savepoint():
            level=self._owner_level(account,character)
            old=self._read(account)
            if old is not None:
                if old.character_uid==character and old.operation==operation:
                    return old
                raise ParticipationConflict('Account already has a participating character')
            if level!=self.definition.minimum_level:
                raise ValueError('Selected activity requires a level99 character')
            self.db.execute('INSERT INTO boosting2026_participation VALUES (?,?,?,?,?,?,?)',
                (account,self.definition.code,character,joined_at,operation,SOURCE_SHA256,
                 self._digest(account,character,operation)))
            return Participation(character,joined_at,operation)
