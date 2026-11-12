"""Account task166210 lifecycle while its original reward mapping is missing.

No successful claim path exists yet: ready tasks survive resets, reconnects and
rejected claim attempts. Ordinary character quest tables are never modified.
Incomplete cross-day progress is retained but frozen for rule investigation;
this module must not be activated as a complete daily quest implementation.
"""
import contextlib
import json


class AttendanceTasks:
    def __init__(self, progress, schedule):
        if (progress.definition.code,progress.definition.quest_id) != (518,166210):
            raise ValueError('Not the selected attendance task')
        self.progress = progress
        self.db = progress.db
        self.schedule = schedule

    def _validate_binding(self):
        if self.db.execute('SELECT definition_sha256 FROM activity518_campaigns WHERE campaign=?',
                           (self.progress.campaign,)).fetchone() != (self.progress.digest,):
            raise ValueError('Campaign definition mismatch')
        actual = tuple(self.db.execute('SELECT period,starts,ends FROM activity518_periods WHERE campaign=? ORDER BY starts',
                                       (self.progress.campaign,)))
        expected = tuple((p.key,p.starts,p.ends) for p in self.schedule.periods)
        if actual != expected:
            raise ValueError('Task schedule must match the installed campaign')

    @contextlib.contextmanager
    def _transaction(self):
        with self.progress._transaction():
            self._validate_binding()
            yield

    def initialize(self):
        with self._transaction():
            self.db.execute('''CREATE TABLE IF NOT EXISTS activity518_tasks(
                campaign TEXT NOT NULL, account INTEGER NOT NULL,
                accepted_period TEXT NOT NULL, accepted_at INTEGER NOT NULL,
                fact_floor INTEGER NOT NULL,
                clears INTEGER NOT NULL DEFAULT 0, seconds INTEGER NOT NULL DEFAULT 0,
                ready_at INTEGER, PRIMARY KEY(campaign,account))''')

    def _owner(self, account, character):
        if any(type(v) is not int or v <= 0 for v in (account,character)):
            raise ValueError('Authenticated account and character required')
        row = self.db.execute('SELECT c.level FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',
                              (character,account)).fetchone()
        if row is None or row[0] < self.progress.definition.minimum_level:
            raise ValueError('Owned level10 character required')

    def _read(self, account):
        row = self.db.execute('SELECT accepted_period,accepted_at,clears,seconds,ready_at FROM activity518_tasks WHERE campaign=? AND account=?',
                              (self.progress.campaign,account)).fetchone()
        if row is None:
            return None
        return dict(quest_id=166210,accepted_period=row[0],accepted_at=row[1],
                    clears=row[2],online_seconds=row[3],ready_at=row[4],
                    ready=row[4] is not None,claimed=False,reward_granted=False,
                    incomplete_carry_rule_pending=False)

    def _refresh(self, account, now):
        state = self._read(account)
        if state is None:
            return None
        if now < state['accepted_at']:
            raise ValueError('Task clock precedes acceptance')
        if state['ready']:
            return state
        # Only the accepted period's proven facts are used. A daily boundary
        # never discards a pending task. Incomplete carry-forward is unresolved.
        bounds = next(p for p in self.schedule.periods if p.key == state['accepted_period'])
        clears = 0
        spans = []
        floor = self.db.execute('SELECT fact_floor FROM activity518_tasks WHERE campaign=? AND account=?',
                                (self.progress.campaign,account)).fetchone()[0]
        facts = self.db.execute('SELECT payload FROM activity518_facts WHERE campaign=? AND account=? AND period=? AND rowid>?',
                                (self.progress.campaign,str(account),state['accepted_period'],floor))
        for (payload,) in facts:
            fact = json.loads(payload)
            if not fact['qualifies']:
                continue
            if fact['kind'] == 'dungeon':
                clears += state['accepted_at'] <= fact['occurred_at'] <= now
            elif fact['kind'] == 'online':
                a,b = max(state['accepted_at'],fact['starts']),min(now,fact['ends'])
                if a < b:
                    spans.append((a,b))
        seconds,last = 0,0
        for a,b in sorted(spans):
            seconds += max(0,b-max(a,last));last=max(last,b)
        clears,seconds = min(5,clears),min(3600,seconds)
        if clears < state['clears'] or seconds < state['online_seconds']:
            raise ValueError('Task progress or authoritative clock moved backwards')
        ready = clears >= 5 or seconds >= 3600
        ready_at = now if ready else None  # observed time, not invented completion time
        self.db.execute('UPDATE activity518_tasks SET clears=?,seconds=?,ready_at=? WHERE campaign=? AND account=?',
                        (clears,seconds,ready_at,self.progress.campaign,account))
        state = self._read(account)
        state['incomplete_carry_rule_pending'] = not ready and now >= bounds.ends
        return state

    def accept(self, *, account, character, now):
        period = self.schedule.period_at(now)
        if period is None:
            raise ValueError('Campaign is unavailable')
        with self._transaction():
            self._owner(account,character)
            old = self._refresh(account,now)
            if old is not None:
                return old
            floor = self.db.execute('SELECT coalesce(max(rowid),0) FROM activity518_facts').fetchone()[0]
            self.db.execute('INSERT INTO activity518_tasks(campaign,account,accepted_period,accepted_at,fact_floor) VALUES (?,?,?,?,?)',
                            (self.progress.campaign,account,period,now,floor))
            return self._read(account)

    def snapshot(self, *, account, character, now):
        self.schedule.period_at(now)  # validate server timestamp, allow archived view
        with self._transaction():
            self._owner(account,character)
            return self._refresh(account,now)

    def claim(self, *, account, character, now):
        """Return a failure, preserve pending progress, never mint a receipt.

        A future verified award implementation must atomically commit the mail,
        attendance state and claim-day lock, then release this pending task.
        The missing mapping must not be replaced with an empty successful award.
        """
        period = self.schedule.period_at(now)
        with self._transaction():
            self._owner(account,character)
            state = self._refresh(account,now)
            if period is None or state is None or not state['ready']:
                return dict(result=187,reason='requirements_not_met',state=state)
            return dict(result=2005,reason='original_reward_mapping_missing',state=state)
