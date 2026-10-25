"""Opt-in monotonic observations for selected coexistence character/week progress.

Eligibility is a required server policy, not a recovered complete CN scene rule.
Persisted explicit periods exclude maintenance gaps. No stored clock anchor can
turn process downtime into online time. This module sends no client packets.
"""
import math
import sqlite3
import logging
import time
import uuid
from contextlib import closing
from els_server.storage.online_2026_progress import OnlineTitleProgress


class OnlineTitleClock:
    def __init__(self, selection_bytes, *, campaign, eligibility,
                 monotonic=time.monotonic, epoch=time.time):
        if not callable(eligibility):
            raise TypeError('Explicit trusted eligibility policy required')
        self.selection_bytes = selection_bytes
        self.campaign, self.eligibility = campaign, eligibility
        self.monotonic, self.epoch = monotonic, epoch
        self.token = uuid.uuid4().hex
        self.identity = None
        self.base = self.anchor = self.cursor = self.last = None
        self.closed = False

    def observe(self, session, *, stop=False):
        if self.closed:
            return
        try:
            self._observe(session, stop=stop)
        except sqlite3.OperationalError as error:
            code=getattr(error,'sqlite_errorcode',None)
            if stop or type(code) is not int or code & 255 not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):raise
            # _persist is atomic and the cursor advances only after commit.
            # Retain that observed interval for the next ordinary observation.
            logging.getLogger(__name__).warning('Online title persistence deferred: SQLite code=%s',code,exc_info=True)
        finally:
            if stop:
                # Even a failed final flush may not accrue post-disconnect time.
                self.closed = True
                self.identity = None

    def _observe(self, session, *, stop):
        mono, wall = self.monotonic(), self.epoch()
        if (any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v < 2**63
                for v in (mono, wall)) or (self.last is not None and mono < self.last)):
            self.identity = None
            raise ValueError('Invalid or backwards server clock')
        self.last = mono
        current = self.eligibility(session)
        if current is not None:
            if (type(current) is not tuple or len(current) != 4 or
                    type(current[0]) is not str or not current[0] or
                    any(type(v) is not int or v < 1 for v in current[1:]) or current[3] < 10):
                self.identity = None
                raise ValueError('Invalid eligible character identity')
        if self.identity is not None:
            elapsed = mono-self.base
            # A pre-operation observation accounts for the old role before its
            # selection changes. If eligibility changes outside those hooks, the
            # unobserved gap is uncertain and is discarded, never reassigned.
            if current == self.identity and abs(wall-(self.anchor+elapsed)) <= 2:
                end = math.floor(self.anchor+elapsed)
                if end > self.cursor:
                    self._persist(self.cursor, end)
                    self.cursor = end  # Only after every weekly slice commits.
            else:
                self.identity = None
        current = None if stop else current
        if current != self.identity or self.identity is None:
            self.identity = current
            self.base, self.anchor = mono, wall
            # Count only full epoch seconds contained in this observed interval.
            self.cursor = math.ceil(wall)

    def _persist(self, start, end):
        path, account, character, _ = self.identity
        with closing(sqlite3.connect(path, timeout=10)) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                repo = OnlineTitleProgress(db, self.selection_bytes, campaign=self.campaign)
                repo._definition()
                if repo._owner(account, character) < 10:
                    raise ValueError('Stored online character is no longer eligible')
                periods = db.execute('''SELECT week,starts,ends FROM online2026_periods
                    WHERE campaign=? AND starts<? AND ends>? ORDER BY starts''',
                    (self.campaign, end, start)).fetchall()
                for week, lo, hi in periods:
                    a, b = max(start, lo), min(end, hi)
                    repo.record_span(account=account, character=character, week=week,
                        operation=f'clock:{self.token}:{start}:{end}:{week}', starts=a, ends=b)
                db.commit()
            except BaseException:
                db.rollback()
                raise
