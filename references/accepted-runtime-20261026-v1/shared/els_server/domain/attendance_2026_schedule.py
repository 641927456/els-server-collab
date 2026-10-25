"""CN daily boundaries for 518, separate from task completion and claiming.

CN official quest guide specifies 10:00 daily. Applying this to the selected
daily quest is a source-based inference; no event-specific exception was found.
Actual maintenance/availability bounds must be supplied explicitly. The guide's
late-claim rule means a boundary alone MUST NOT reopen or award a task.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

CN = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class DailyPeriod:
    index: int
    label: str
    starts: int
    ends: int

    @property
    def key(self):
        return 'day:' + self.label


@dataclass(frozen=True)
class AttendanceSchedule:
    purpose: str
    first_date: date
    available_from: int
    available_until: int
    periods: tuple

    @classmethod
    def build(cls, *, purpose, first_date, available_from, available_until):
        if purpose not in ('cn_2026_historical', 'explicit_local_test'):
            raise ValueError('Schedule purpose must be explicit')
        if type(first_date) is not date:
            raise ValueError('First reward date required')
        if purpose == 'cn_2026_historical' and first_date != date(2026,6,17):
            raise ValueError('Not the selected 2026 CN campaign')
        if any(type(x) is not int or x < 0 for x in (available_from,available_until)):
            raise ValueError('Availability requires explicit epoch seconds')
        base = int(datetime.combine(first_date,time(10),CN).timestamp())
        end = base + 42 * 86400
        if not base <= available_from < available_until <= end:
            raise ValueError('Availability must fit the 42 selected reward days')
        periods = []
        for i in range(42):
            starts = max(available_from,base+i*86400)
            ends = min(available_until,base+(i+1)*86400)
            if starts < ends:
                periods.append(DailyPeriod(i,(first_date+timedelta(days=i)).isoformat(),starts,ends))
        return cls(purpose,first_date,available_from,available_until,tuple(periods))

    def period_at(self, timestamp):
        if type(timestamp) is not int:
            raise ValueError('Server epoch seconds required')
        return next((p.key for p in self.periods if p.starts <= timestamp < p.ends),None)

    def split(self, starts, ends):
        """Clip observed spans at every daily boundary; no online eligibility."""
        if any(type(x) is not int or x < 0 for x in (starts,ends)) or starts > ends:
            raise ValueError('Invalid observed interval')
        return tuple((p.key,max(starts,p.starts),min(ends,p.ends)) for p in self.periods
                     if max(starts,p.starts) < min(ends,p.ends))

    def install(self, progress):
        """Bind the full schedule atomically; never mutate an existing period."""
        expected = {p.key:(p.starts,p.ends) for p in self.periods}
        with progress._transaction():
            campaign = progress.db.execute('SELECT definition_sha256 FROM activity518_campaigns WHERE campaign=?', (progress.campaign,)).fetchone()
            if campaign != (progress.digest,):
                raise ValueError('Initialize the matching campaign first')
            old = dict((key,(a,b)) for key,a,b in progress.db.execute('SELECT period,starts,ends FROM activity518_periods WHERE campaign=?',(progress.campaign,)))
            if any(key not in expected or expected[key] != value for key,value in old.items()):
                raise ValueError('Existing period belongs to a different schedule')
            progress.db.executemany('INSERT OR IGNORE INTO activity518_periods VALUES (?,?,?,?)',
                [(progress.campaign,p.key,p.starts,p.ends) for p in self.periods])
