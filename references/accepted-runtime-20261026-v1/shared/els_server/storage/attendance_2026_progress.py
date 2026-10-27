"""Account-scoped progress ledger for selected 518; no stamps or grants yet.

The session supplies authoritative period boundaries and server-observed facts.
This layer deliberately cannot select a reset time, mutate ED, mint mail, mark
reward bits or open an event. Missing reward maps remain unresolved. It can be
integrated with the final task/mail transaction after those rules are recovered.
"""
import contextlib
import hashlib
import json
import sqlite3


def _key(value):
    if type(value) is not str or not value or len(value) > 160:
        raise ValueError('Invalid progress identity')
    return value


def _number(value):
    if type(value) is not int or not 0 <= value < (1 << 63):
        raise ValueError('Invalid authoritative progress number')
    return value


class AttendanceProgress:
    def __init__(self, connection, definition, *, campaign_id, definition_sha256):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError('A caller-owned SQLite connection is required')
        self.db = connection
        self.definition = definition
        self.campaign = _key(campaign_id)
        if (type(definition_sha256) is not str or len(definition_sha256) != 64
                or any(c not in '0123456789abcdef' for c in definition_sha256)):
            raise ValueError('Original definition SHA256 is required')
        self.digest = definition_sha256

    @contextlib.contextmanager
    def _transaction(self):
        if self.db.in_transaction:
            raise RuntimeError('Progress transaction cannot commit another operation')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def initialize(self):
        with self._transaction():
            for sql in (
                '''CREATE TABLE IF NOT EXISTS activity518_campaigns(
                    campaign TEXT PRIMARY KEY, definition_sha256 TEXT NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS activity518_periods(
                    campaign TEXT NOT NULL, period TEXT NOT NULL,
                    starts INTEGER NOT NULL, ends INTEGER NOT NULL,
                    PRIMARY KEY(campaign,period))''',
                '''CREATE TABLE IF NOT EXISTS activity518_facts(
                    campaign TEXT NOT NULL, account TEXT NOT NULL, operation TEXT NOT NULL,
                    period TEXT NOT NULL, payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    PRIMARY KEY(campaign,account,operation))''',
                '''CREATE TABLE IF NOT EXISTS activity518_progress(
                    campaign TEXT NOT NULL, account TEXT NOT NULL, period TEXT NOT NULL,
                    dungeon_clears INTEGER NOT NULL, online_seconds INTEGER NOT NULL,
                    PRIMARY KEY(campaign,account,period))'''):
                self.db.execute(sql)
            old = self.db.execute('SELECT definition_sha256 FROM activity518_campaigns WHERE campaign=?', (self.campaign,)).fetchone()
            if old and old[0] != self.digest:
                raise ValueError('Campaign definition changed; preserve existing progress')
            self.db.execute('INSERT OR IGNORE INTO activity518_campaigns VALUES (?,?)', (self.campaign,self.digest))

    def register_period(self, period, starts, ends):
        """Explicit caller-supplied period; no default reset hour or auto rollover."""
        _key(period);_number(starts);_number(ends)
        if starts >= ends:
            raise ValueError('Invalid period boundaries')
        with self._transaction():
            old = self.db.execute('SELECT starts,ends FROM activity518_periods WHERE campaign=? AND period=?', (self.campaign,period)).fetchone()
            if old and tuple(old) != (starts,ends):
                raise ValueError('Cannot change an existing progress period')
            overlap = self.db.execute('SELECT 1 FROM activity518_periods WHERE campaign=? AND period<>? AND starts<? AND ends>?', (self.campaign,period,ends,starts)).fetchone()
            if overlap:
                raise ValueError('Account progress periods must not overlap')
            self.db.execute('INSERT OR IGNORE INTO activity518_periods VALUES (?,?,?,?)', (self.campaign,period,starts,ends))

    def snapshot(self, account, period):
        _key(account);_key(period)
        row = self.db.execute('SELECT dungeon_clears,online_seconds FROM activity518_progress WHERE campaign=? AND account=? AND period=?', (self.campaign,account,period)).fetchone()
        clears,seconds = row if row else (0,0)
        return dict(dungeon_clears=clears,online_seconds=seconds,
                    counter_condition_met=(clears >= 5 or seconds >= 3600),
                    stamp_committed=False,reward_granted=False)

    def record_dungeon(self, *, account, period, operation, character, level,
                       occurred_at, dungeon_id, appropriate_level):
        _number(occurred_at);_number(dungeon_id)
        allowed = self.definition.counts_as_dungeon_clear(dungeon_id,appropriate_level=appropriate_level)
        return self._record(account,period,operation,character,level,
                            dict(kind='dungeon',occurred_at=occurred_at,dungeon_id=dungeon_id,
                                 appropriate_level=appropriate_level,qualifies=allowed))

    def record_dungeon_atomic(self, *, account, period, operation, character, level,
                              occurred_at, dungeon_id, appropriate_level):
        """Join an existing clear transaction; never commit or roll it back."""
        if not self.db.in_transaction:
            raise RuntimeError('Caller-owned clear transaction required')
        _number(occurred_at);_number(dungeon_id)
        allowed = self.definition.counts_as_dungeon_clear(dungeon_id, appropriate_level=appropriate_level)
        return self._record(account,period,operation,character,level,
                            dict(kind='dungeon',occurred_at=occurred_at,dungeon_id=dungeon_id,
                                 appropriate_level=appropriate_level,qualifies=allowed), join_transaction=True)

    def record_online(self, *, account, period, operation, character, level, starts, ends):
        _number(starts);_number(ends)
        if starts >= ends:
            raise ValueError('An observed online interval must have positive duration')
        return self._record(account,period,operation,character,level,
                            dict(kind='online',starts=starts,ends=ends,qualifies=True))

    def _record(self, account, period, operation, character, level, fact, *, join_transaction=False):
        _key(account);_key(period);_key(operation);_key(character);_number(level)
        fact.update(character=character,level=level,period=period)
        fact['qualifies'] = fact['qualifies'] and level >= self.definition.minimum_level
        payload = json.dumps(fact,sort_keys=True,separators=(',',':'))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with (contextlib.nullcontext() if join_transaction else self._transaction()):
            old = self.db.execute('SELECT payload_sha256 FROM activity518_facts WHERE campaign=? AND account=? AND operation=?', (self.campaign,account,operation)).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError('Operation identity reused for different facts')
                return self.snapshot(account,period)
            bounds = self.db.execute('SELECT starts,ends FROM activity518_periods WHERE campaign=? AND period=?', (self.campaign,period)).fetchone()
            if not bounds:
                raise ValueError('Authoritative period is not registered')
            if fact['kind'] == 'online':
                valid = bounds[0] <= fact['starts'] < fact['ends'] <= bounds[1]
            else:
                valid = bounds[0] <= fact['occurred_at'] < bounds[1]
            if not valid:
                raise ValueError('Fact crosses or falls outside the authoritative period')
            self.db.execute('INSERT INTO activity518_facts VALUES (?,?,?,?,?,?)', (self.campaign,account,operation,period,payload,digest))
            facts = [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM activity518_facts WHERE campaign=? AND account=? AND period=?', (self.campaign,account,period))]
            clears = min(5,sum(f['kind']=='dungeon' and f['qualifies'] for f in facts))
            spans = sorted((f['starts'],f['ends']) for f in facts if f['kind']=='online' and f['qualifies'])
            seconds = 0
            last_end = None
            for begin,end in spans:
                seconds += max(0,end-max(begin,last_end if last_end is not None else begin))
                last_end = max(end,last_end if last_end is not None else end)
            self.db.execute('INSERT INTO activity518_progress VALUES (?,?,?,?,?) ON CONFLICT(campaign,account,period) DO UPDATE SET dungeon_clears=excluded.dungeon_clears,online_seconds=excluded.online_seconds', (self.campaign,account,period,clears,min(3600,seconds)))
            return self.snapshot(account,period)
