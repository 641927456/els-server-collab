"""Character-owned resonance pages for the isolated 2026 candidate.

Provisioning requires every page's explicit authoritative point state. This
module derives no opening, level-to-points, expansion cost or temporary bonus.
Selection is storage-only; callers must validate original gameplay eligibility.
No live request handler or GM grant endpoint uses this candidate yet.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import sqlite3
import uuid

from els_server.domain.resonance_2026_allocations import ResonanceAllocations, DEFINITION_SHA256
from els_server.protocol.resonance_2026_request import ResonanceAllocationRequest


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid resonance integer')
    return value


def packed(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True)


@dataclass(frozen=True)
class ResonancePage:
    page_id: int
    available_points: int
    points: tuple


@dataclass(frozen=True)
class CharacterResonancePages:
    revision: int
    enabled: bool
    selected_page: int
    pages: tuple

    def selected(self):
        return next(p for p in self.pages if p.page_id == self.selected_page)


class PageConflict(ValueError):
    pass


class ResonancePages:
    def __init__(self, connection, original_definition):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError('Caller-owned SQLite connection required')
        self.db = connection
        self.rules = ResonanceAllocations.from_original(original_definition)

    @contextmanager
    def transaction(self):
        outer = self.db.in_transaction
        name = 'resonance_pages_' + uuid.uuid4().hex
        self.db.execute('SAVEPOINT ' + name if outer else 'BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('RELEASE ' + name) if outer else self.db.commit()
        except BaseException:
            if outer:
                self.db.execute('ROLLBACK TO ' + name)
                self.db.execute('RELEASE ' + name)
            else:
                self.db.rollback()
            raise

    def initialize(self):
        with self.transaction():
            self.db.execute('''CREATE TABLE IF NOT EXISTS resonance2026_characters(
                character INTEGER PRIMARY KEY CHECK(character>0),
                account INTEGER NOT NULL CHECK(account>0),
                revision INTEGER NOT NULL CHECK(revision>0),
                definition_sha256 TEXT NOT NULL, state_json TEXT NOT NULL)''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS resonance2026_page_receipts(
                character INTEGER NOT NULL, operation TEXT NOT NULL,
                request_sha256 TEXT NOT NULL, revision INTEGER NOT NULL,
                result_json TEXT NOT NULL, PRIMARY KEY(character,operation))''')

    def owner(self, account, character):
        integer(account, 1, 2**63-1); integer(character, 1, 2**63-1)
        if self.db.execute('''SELECT 1 FROM character_owners o JOIN characters c
            ON c.uid=o.uid WHERE o.account_id=? AND o.uid=?''', (account, character)).fetchone() is None:
            raise ValueError('Character does not belong to authenticated account')

    def validate(self, state):
        if type(state) is not CharacterResonancePages or type(state.enabled) is not bool:
            raise ValueError('Explicit character resonance state required')
        integer(state.revision, 1, 2**63-1)
        if type(state.pages) is not tuple or not 1 <= len(state.pages) <= 4:
            raise ValueError('Explicit opened page states required')
        integer(state.selected_page, 1, len(state.pages))
        normalized = []
        for page_id, page in enumerate(state.pages, 1):
            if type(page) is not ResonancePage or type(page.page_id) is not int or page.page_id != page_id:
                raise ValueError('Pages must be complete and ordered')
            plan = self.rules.add(current=page.points, additions=(),
                                  available_points=page.available_points, bonus_points=())
            normalized.append(ResonancePage(page_id, plan.remaining_points, plan.points))
        return CharacterResonancePages(state.revision, state.enabled, state.selected_page, tuple(normalized))

    def encode(self, state):
        state = self.validate(state)
        return packed([state.revision, state.enabled, state.selected_page,
                       [[p.page_id, p.available_points, p.points] for p in state.pages]])

    def decode(self, raw):
        try:
            revision, enabled, selected, pages = json.loads(raw)
            state = CharacterResonancePages(revision, enabled, selected,
                tuple(ResonancePage(p[0], p[1], tuple(tuple(v) for v in p[2])) for p in pages))
            return self.validate(state)
        except (TypeError, IndexError, KeyError) as error:
            raise ValueError('Invalid stored resonance pages') from error

    def read(self, account, character):
        row = self.db.execute('''SELECT account,revision,definition_sha256,state_json
            FROM resonance2026_characters WHERE character=?''', (character,)).fetchone()
        if row is None:
            return None
        if row[0] != account or row[2] != DEFINITION_SHA256:
            raise ValueError('Stored page owner or definition differs')
        result = self.decode(row[3])
        if result.revision != row[1]:
            raise ValueError('Stored page revision differs')
        return result

    def snapshot(self, *, account, character):
        with self.transaction():
            self.owner(account, character)
            return self.read(account, character)

    def mutate(self, *, account, character, operation, expected_revision, kind, inputs, change):
        if type(operation) is not str or not 1 <= len(operation) <= 160:
            raise ValueError('Stable authoritative operation identity required')
        integer(expected_revision, 0, 2**63-2)
        digest = hashlib.sha256(packed([account, character, expected_revision,
                                        kind, inputs, DEFINITION_SHA256]).encode()).hexdigest()
        with self.transaction():
            self.owner(account, character)
            current = self.read(account, character)
            old = self.db.execute('''SELECT request_sha256,revision,result_json
                FROM resonance2026_page_receipts WHERE character=? AND operation=?''',
                (character, operation)).fetchone()
            if old:
                if digest != old[0] or current is None or current.revision < old[1]:
                    raise PageConflict('Conflicting receipt or missing committed state')
                result = self.decode(old[2])
                if result.revision != old[1]:
                    raise PageConflict('Receipt revision differs')
                return result
            if (current.revision if current else 0) != expected_revision:
                raise PageConflict('Stale character resonance revision')
            result = self.validate(change(current, expected_revision+1))
            raw = self.encode(result)
            self.db.execute('''INSERT INTO resonance2026_characters VALUES(?,?,?,?,?)
                ON CONFLICT(character) DO UPDATE SET revision=excluded.revision,
                state_json=excluded.state_json''',
                (character, account, result.revision, DEFINITION_SHA256, raw))
            self.db.execute('INSERT INTO resonance2026_page_receipts VALUES(?,?,?,?,?)',
                (character, operation, digest, result.revision, raw))
            return result

    def provision(self, *, account, character, operation, enabled, selected_page, pages):
        """Store a trusted complete initial snapshot; never infer or replace it."""
        initial = self.validate(CharacterResonancePages(1, enabled, selected_page, pages))
        def change(current, revision):
            if current is not None:
                raise PageConflict('Character already has resonance pages')
            return initial
        return self.mutate(account=account, character=character, operation=operation,
            expected_revision=0, kind='provision', inputs=self.encode(initial), change=change)

    def allocate(self, *, account, character, operation, expected_revision, payload, bonus_points):
        request = ResonanceAllocationRequest.decode(payload)
        # Validate all explicit bonus input before serializing it into the receipt.
        bonus = tuple(sorted(self.rules._points(bonus_points, bonus=True).items()))
        def change(current, revision):
            if current is None or not current.enabled:
                raise ValueError('Resonance is not initialized and enabled')
            page = current.selected()
            plan = request.plan_positive(rules=self.rules, selected_page=current.selected_page,
                current=page.points, available_points=page.available_points, bonus_points=bonus)
            pages = tuple(ResonancePage(p.page_id, plan.remaining_points, plan.points)
                          if p.page_id == page.page_id else p for p in current.pages)
            return CharacterResonancePages(revision, current.enabled, current.selected_page, pages)
        return self.mutate(account=account, character=character, operation=operation,
            expected_revision=expected_revision, kind='allocate',
            inputs=[payload.hex(), bonus], change=change)

    def select(self, *, account, character, operation, expected_revision, selected_page):
        """Select an existing stored page after caller verifies gameplay gates."""
        integer(selected_page, 1, 4)
        def change(current, revision):
            if current is None or not current.enabled or selected_page > len(current.pages):
                raise ValueError('Resonance page is not available')
            return CharacterResonancePages(revision, current.enabled, selected_page, current.pages)
        return self.mutate(account=account, character=character, operation=operation,
            expected_revision=expected_revision, kind='select', inputs=selected_page, change=change)
